#!/usr/bin/env python3
"""Generate a one-process Minecraft-like runtime directly inside sm64-port.

Universal Modder mashup Pattern 4: reimplement, then fuse.
No Fabric guest, WebSocket, shared memory or second game process is used.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SM64 = ROOT / "vendor" / "sm64-port"
PC = SM64 / "src" / "pc"
GFX = PC / "gfx"
NM = PC / "native_minecraft"


def patch_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch marker missing in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if not (SM64 / "src" / "game" / "mario.c").is_file():
    raise SystemExit("Run setup-windows.bat first.")

NM.mkdir(parents=True, exist_ok=True)

(NM / "native_minecraft.h").write_text(r'''#pragma once

#ifdef __cplusplus
extern "C" {
#endif

struct MarioState;

void native_minecraft_tick(struct MarioState *m);
void native_minecraft_apply_proxy(struct MarioState *m);
void native_minecraft_override_camera(void);
int native_minecraft_active(void);
int native_minecraft_first_person(void);
int native_minecraft_selected_slot(void);
int native_minecraft_block_count(void);
int native_minecraft_get_block(int index, int *x, int *y, int *z, int *type);
void native_minecraft_get_render_state(
    float *x, float *y, float *z,
    float *yaw, float *pitch,
    int *first_person, int *selected_slot
);

#ifdef __cplusplus
}
#endif
''', encoding="utf-8")

(NM / "native_minecraft.cpp").write_text(r'''#include "native_minecraft.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#ifdef near
#undef near
#endif
#ifdef far
#undef far
#endif

extern "C" {
#include "sm64.h"
#include "engine/math_util.h"
#include "engine/surface_collision.h"
#include "game/area.h"
#include "game/camera.h"
#include "game/level_update.h"
#include "game/mario.h"
}

namespace {

constexpr float BLOCK = 100.0f;
constexpr float PLAYER_RADIUS = 30.0f;
constexpr float PLAYER_HEIGHT = 180.0f;
constexpr float EYE_HEIGHT = 162.0f;

// Minecraft Java movement approximated at SM64's 30 Hz host tick.
constexpr float WALK_SPEED = 14.3f;
constexpr float SPRINT_SPEED = 18.3f;
constexpr float SNEAK_SPEED = 4.3f;
constexpr float AIR_ACCEL = 2.0f;
constexpr float GROUND_ACCEL = 6.5f;
constexpr float GRAVITY = 5.35f;
constexpr float JUMP_VELOCITY = 28.0f;
constexpr float MAX_FALL = 78.0f;

struct NativePlayer {
    bool initialized = false;
    bool firstPerson = false;
    bool onGround = false;
    int level = -1;
    int area = -1;
    int selectedSlot = 0;

    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float vx = 0.0f;
    float vy = 0.0f;
    float vz = 0.0f;
    float yaw = 0.0f;
    float pitch = 0.0f;
};

NativePlayer gPlayer;

struct NativeBlock {
    int x;
    int y;
    int z;
    int type;
};

std::vector<NativeBlock> gBlocks;

bool host_has_focus() {
    HWND hwnd = GetForegroundWindow();
    if (!hwnd) return false;
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    return pid == GetCurrentProcessId();
}

bool key_down(int vk) {
    return host_has_focus() && (GetAsyncKeyState(vk) & 0x8000) != 0;
}

bool key_pressed(int vk) {
    return host_has_focus() && (GetAsyncKeyState(vk) & 0x0001) != 0;
}

float radians(float degrees) {
    return degrees * 0.01745329251994329577f;
}

void capture_mouse() {
    if (!host_has_focus()) return;

    HWND hwnd = GetForegroundWindow();
    RECT rect{};
    if (!hwnd || !GetClientRect(hwnd, &rect)) return;

    POINT center{
        (rect.right - rect.left) / 2,
        (rect.bottom - rect.top) / 2
    };
    POINT screenCenter = center;
    ClientToScreen(hwnd, &screenCenter);

    POINT cursor{};
    if (!GetCursorPos(&cursor)) return;

    const int dx = cursor.x - screenCenter.x;
    const int dy = cursor.y - screenCenter.y;

    // Close to the vanilla default sensitivity feel, but native and stable.
    constexpr float SENSITIVITY = 0.15f;
    gPlayer.yaw += static_cast<float>(dx) * SENSITIVITY;
    gPlayer.pitch += static_cast<float>(dy) * SENSITIVITY;
    gPlayer.pitch = std::clamp(gPlayer.pitch, -89.0f, 89.0f);

    while (gPlayer.yaw >= 180.0f) gPlayer.yaw -= 360.0f;
    while (gPlayer.yaw < -180.0f) gPlayer.yaw += 360.0f;

    SetCursorPos(screenCenter.x, screenCenter.y);
}

void initialize_from_mario(MarioState *m) {
    gPlayer.initialized = true;
    gPlayer.level = gCurrLevelNum;
    gPlayer.area = gCurrAreaIndex;
    gPlayer.x = m->pos[0];
    gPlayer.y = m->pos[1];
    gPlayer.z = m->pos[2];
    gPlayer.vx = gPlayer.vy = gPlayer.vz = 0.0f;
    gPlayer.yaw =
        180.0f - static_cast<float>(m->faceAngle[1]) * (360.0f / 65536.0f);
    gPlayer.pitch = 0.0f;
    gPlayer.onGround = true;
}

void update_hotbar_and_view() {
    for (int i = 0; i < 9; ++i) {
        if (key_pressed('1' + i)) {
            gPlayer.selectedSlot = i;
        }
    }
    if (key_pressed(VK_F5)) {
        gPlayer.firstPerson = !gPlayer.firstPerson;
    }
}

void collide_horizontal(float &x, float &y, float &z) {
    WallCollisionData walls{};
    walls.x = x;
    walls.y = y;
    walls.z = z;
    walls.offsetY = PLAYER_HEIGHT * 0.5f;
    walls.radius = PLAYER_RADIUS;
    find_wall_collisions(&walls);
    x = walls.x;
    y = walls.y;
    z = walls.z;
}

void simulate_movement() {
    const bool forward = key_down('W');
    const bool backward = key_down('S');
    const bool left = key_down('A');
    const bool right = key_down('D');
    const bool sneak = key_down(VK_SHIFT);
    const bool sprint = key_down(VK_CONTROL) && forward && !sneak;

    float inputForward = (forward ? 1.0f : 0.0f) - (backward ? 1.0f : 0.0f);
    float inputStrafe = (right ? 1.0f : 0.0f) - (left ? 1.0f : 0.0f);

    float length = std::sqrt(
        inputForward * inputForward + inputStrafe * inputStrafe
    );
    if (length > 1.0f) {
        inputForward /= length;
        inputStrafe /= length;
    }

    const float speed = sneak
        ? SNEAK_SPEED
        : (sprint ? SPRINT_SPEED : WALK_SPEED);

    const float yaw = radians(gPlayer.yaw);
    const float sinYaw = std::sin(yaw);
    const float cosYaw = std::cos(yaw);

    const float wishX =
        (-sinYaw * inputForward + cosYaw * inputStrafe) * speed;
    const float wishZ =
        ( cosYaw * inputForward + sinYaw * inputStrafe) * speed;

    const float accel = gPlayer.onGround ? GROUND_ACCEL : AIR_ACCEL;
    gPlayer.vx += std::clamp(wishX - gPlayer.vx, -accel, accel);
    gPlayer.vz += std::clamp(wishZ - gPlayer.vz, -accel, accel);

    if (length == 0.0f && gPlayer.onGround) {
        gPlayer.vx *= 0.60f;
        gPlayer.vz *= 0.60f;
        if (std::fabs(gPlayer.vx) < 0.02f) gPlayer.vx = 0.0f;
        if (std::fabs(gPlayer.vz) < 0.02f) gPlayer.vz = 0.0f;
    }

    if (gPlayer.onGround && key_pressed(VK_SPACE)) {
        gPlayer.vy = JUMP_VELOCITY;
        gPlayer.onGround = false;
    } else {
        const float falling = gPlayer.vy - GRAVITY;
        gPlayer.vy = falling > -MAX_FALL ? falling : -MAX_FALL;
    }

    float nextX = gPlayer.x + gPlayer.vx;
    float nextY = gPlayer.y + gPlayer.vy;
    float nextZ = gPlayer.z + gPlayer.vz;

    collide_horizontal(nextX, nextY, nextZ);

    Surface *floor = nullptr;
    const float floorY = find_floor(
        nextX, nextY + PLAYER_HEIGHT, nextZ, &floor
    );

    Surface *ceil = nullptr;
    const float ceilY = find_ceil(
        nextX, nextY + 80.0f, nextZ, &ceil
    );

    if (gPlayer.vy <= 0.0f
        && floor != nullptr
        && floorY > FLOOR_LOWER_LIMIT
        && nextY <= floorY + 18.0f
        && gPlayer.y >= floorY - 80.0f) {
        nextY = floorY;
        gPlayer.vy = 0.0f;
        gPlayer.onGround = true;
    } else {
        gPlayer.onGround = false;
    }

    if (gPlayer.vy > 0.0f
        && ceil != nullptr
        && ceilY < CELL_HEIGHT_LIMIT
        && nextY + PLAYER_HEIGHT >= ceilY) {
        nextY = ceilY - PLAYER_HEIGHT;
        gPlayer.vy = 0.0f;
    }

    // Never let an invalid collision query throw the native player into the void.
    if (floor == nullptr && nextY < gPlayer.y - 300.0f) {
        nextX = gPlayer.x;
        nextY = gPlayer.y;
        nextZ = gPlayer.z;
        gPlayer.vx = gPlayer.vy = gPlayer.vz = 0.0f;
    }

    gPlayer.x = nextX;
    gPlayer.y = nextY;
    gPlayer.z = nextZ;
}

} // namespace

extern "C" int native_minecraft_active(void) {
    return gPlayer.initialized ? 1 : 0;
}

extern "C" int native_minecraft_first_person(void) {
    return gPlayer.firstPerson ? 1 : 0;
}

extern "C" int native_minecraft_selected_slot(void) {
    return gPlayer.selectedSlot;
}

extern "C" void native_minecraft_get_render_state(
    float *x, float *y, float *z,
    float *yaw, float *pitch,
    int *first_person, int *selected_slot
) {
    if (x) *x = gPlayer.x;
    if (y) *y = gPlayer.y;
    if (z) *z = gPlayer.z;
    if (yaw) *yaw = gPlayer.yaw;
    if (pitch) *pitch = gPlayer.pitch;
    if (first_person) *first_person = gPlayer.firstPerson ? 1 : 0;
    if (selected_slot) *selected_slot = gPlayer.selectedSlot;
}

extern "C" void native_minecraft_tick(MarioState *m) {
    if (!m || !m->marioObj || gCurrentArea == nullptr) return;

    if (!gPlayer.initialized
        || gPlayer.level != gCurrLevelNum
        || gPlayer.area != gCurrAreaIndex) {
        initialize_from_mario(m);
    }

    capture_mouse();
    update_hotbar_and_view();
    simulate_movement();
    native_minecraft_apply_proxy(m);
}

extern "C" void native_minecraft_apply_proxy(MarioState *m) {
    if (!m || !m->marioObj || !gPlayer.initialized) return;

    Surface *floor = nullptr;
    const float floorY = find_floor(
        gPlayer.x, gPlayer.y + PLAYER_HEIGHT, gPlayer.z, &floor
    );
    if (floor == nullptr || floorY <= FLOOR_LOWER_LIMIT) {
        return;
    }

    constexpr float ANGLE = 65536.0f / 360.0f;
    const float sm64Yaw = 180.0f - gPlayer.yaw;

    m->pos[0] = gPlayer.x;
    m->pos[1] = gPlayer.y;
    m->pos[2] = gPlayer.z;
    m->vel[0] = gPlayer.vx;
    m->vel[1] = gPlayer.vy;
    m->vel[2] = gPlayer.vz;
    m->forwardVel = std::sqrt(
        gPlayer.vx * gPlayer.vx + gPlayer.vz * gPlayer.vz
    );
    m->faceAngle[0] = 0;
    m->faceAngle[1] = static_cast<s16>(sm64Yaw * ANGLE);
    m->faceAngle[2] = 0;
    m->floor = floor;
    m->floorHeight = floorY;

    m->marioObj->oPosX = m->pos[0];
    m->marioObj->oPosY = m->pos[1];
    m->marioObj->oPosZ = m->pos[2];
    m->marioObj->header.gfx.pos[0] = m->pos[0];
    m->marioObj->header.gfx.pos[1] = m->pos[1];
    m->marioObj->header.gfx.pos[2] = m->pos[2];
    m->marioObj->header.gfx.angle[1] = m->faceAngle[1];

    // Mario remains the invisible SM64 trigger/warp/star proxy.
    m->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;
}

extern "C" void native_minecraft_override_camera(void) {
    if (!gPlayer.initialized || gCamera == nullptr) return;

    const float yaw = radians(gPlayer.yaw);
    const float pitch = radians(gPlayer.pitch);
    const float cp = std::cos(pitch);

    const float fx = -std::sin(yaw) * cp;
    const float fy = -std::sin(pitch);
    const float fz = -std::cos(yaw) * cp;

    const float eyeX = gPlayer.x;
    const float eyeY = gPlayer.y + EYE_HEIGHT;
    const float eyeZ = gPlayer.z;

    const float distance = gPlayer.firstPerson ? 0.0f : 400.0f;

    Vec3f pos = {
        eyeX - fx * distance,
        eyeY - fy * distance,
        eyeZ - fz * distance,
    };
    Vec3f focus = {
        eyeX + fx * 200.0f,
        eyeY + fy * 200.0f,
        eyeZ + fz * 200.0f,
    };

    vec3f_copy(gLakituState.curPos, pos);
    vec3f_copy(gLakituState.pos, pos);
    vec3f_copy(gLakituState.goalPos, pos);
    vec3f_copy(gLakituState.curFocus, focus);
    vec3f_copy(gLakituState.focus, focus);
    vec3f_copy(gLakituState.goalFocus, focus);
    vec3f_copy(gCamera->pos, pos);
    vec3f_copy(gCamera->focus, focus);
    gLakituState.roll = 0;
}
''', encoding="utf-8")

# A small native D3D11 renderer: blocky Steve in third person plus Minecraft-like
# first-person arm, crosshair and nine-slot hotbar.  It intentionally uses flat
# colours so no Mojang retail assets are committed.
(GFX / "native_minecraft_render.inc").write_text(r'''
struct NmVertex {
    float x, y, z;
    float r, g, b, a;
};

struct NmPoint {
    float x, y, z;
};

struct NmFace {
    NmVertex v[6];
    float depth;
};

static ComPtr<ID3D11VertexShader> nm_vs;
static ComPtr<ID3D11PixelShader> nm_ps;
static ComPtr<ID3D11InputLayout> nm_layout;
static ComPtr<ID3D11Buffer> nm_vb;
static ComPtr<ID3D11BlendState> nm_blend;
static ComPtr<ID3D11DepthStencilState> nm_no_depth;
static std::vector<NmVertex> nm_vertices;
static std::vector<NmFace> nm_faces;
static bool nm_pipeline_ready = false;

static float nm_px, nm_py, nm_pz, nm_yaw, nm_pitch;
static int nm_first_person, nm_slot;

static void nm_push_tri(const NmVertex &a, const NmVertex &b, const NmVertex &c) {
    nm_vertices.push_back(a);
    nm_vertices.push_back(b);
    nm_vertices.push_back(c);
}

static void nm_push_rect_ndc(float x0, float y0, float x1, float y1,
                             float r, float g, float b, float a) {
    NmVertex v0{x0,y0,0,r,g,b,a}, v1{x1,y0,0,r,g,b,a};
    NmVertex v2{x1,y1,0,r,g,b,a}, v3{x0,y1,0,r,g,b,a};
    nm_push_tri(v0,v1,v2);
    nm_push_tri(v0,v2,v3);
}

static void nm_push_rect_px(float x, float y, float w, float h,
                            float r, float g, float b, float a) {
    const float ww = (float)d3d.current_width;
    const float hh = (float)d3d.current_height;
    const float x0 = x / ww * 2.0f - 1.0f;
    const float x1 = (x+w) / ww * 2.0f - 1.0f;
    const float y0 = 1.0f - y / hh * 2.0f;
    const float y1 = 1.0f - (y+h) / hh * 2.0f;
    nm_push_rect_ndc(x0,y0,x1,y1,r,g,b,a);
}

static bool nm_project(const NmPoint &p, NmVertex &out,
                       float r, float g, float b, float a,
                       float *depth_out) {
    const float DEG = 0.01745329251994329577f;
    const float yaw = nm_yaw * DEG;
    const float pitch = nm_pitch * DEG;
    const float cp = std::cos(pitch);

    const NmPoint forward{
        -std::sin(yaw) * cp,
        -std::sin(pitch),
        -std::cos(yaw) * cp
    };
    const NmPoint right{std::cos(yaw), 0.0f, -std::sin(yaw)};
    const NmPoint up{
        right.y * forward.z - right.z * forward.y,
        right.z * forward.x - right.x * forward.z,
        right.x * forward.y - right.y * forward.x
    };

    const float eyeX = nm_px;
    const float eyeY = nm_py + 162.0f;
    const float eyeZ = nm_pz;
    const float distance = nm_first_person ? 0.0f : 400.0f;
    const NmPoint cam{
        eyeX - forward.x * distance,
        eyeY - forward.y * distance,
        eyeZ - forward.z * distance
    };

    const NmPoint rel{p.x-cam.x, p.y-cam.y, p.z-cam.z};
    const float vx = rel.x*right.x + rel.y*right.y + rel.z*right.z;
    const float vy = rel.x*up.x + rel.y*up.y + rel.z*up.z;
    const float vz = rel.x*forward.x + rel.y*forward.y + rel.z*forward.z;
    if (vz < 8.0f) return false;

    const float tanHalf = std::tan(70.0f * DEG * 0.5f);
    const float aspect = (float)d3d.current_width / (float)d3d.current_height;
    out.x = vx / (vz * tanHalf * aspect);
    out.y = vy / (vz * tanHalf);
    out.z = 0.0f;
    out.r=r; out.g=g; out.b=b; out.a=a;
    if (depth_out) *depth_out = vz;
    return out.x > -3.0f && out.x < 3.0f && out.y > -3.0f && out.y < 3.0f;
}

static NmPoint nm_rotate_local(float lx, float ly, float lz) {
    const float a = (180.0f - nm_yaw) * 0.01745329251994329577f;
    const float s = std::sin(a), co = std::cos(a);
    return NmPoint{
        nm_px + lx * co + lz * s,
        nm_py + ly,
        nm_pz - lx * s + lz * co
    };
}

static void nm_add_box(float cx, float cy, float cz,
                       float sx, float sy, float sz,
                       float r, float g, float b) {
    const float hx=sx*0.5f, hy=sy*0.5f, hz=sz*0.5f;
    NmPoint p[8] = {
        nm_rotate_local(cx-hx,cy-hy,cz-hz),
        nm_rotate_local(cx+hx,cy-hy,cz-hz),
        nm_rotate_local(cx+hx,cy+hy,cz-hz),
        nm_rotate_local(cx-hx,cy+hy,cz-hz),
        nm_rotate_local(cx-hx,cy-hy,cz+hz),
        nm_rotate_local(cx+hx,cy-hy,cz+hz),
        nm_rotate_local(cx+hx,cy+hy,cz+hz),
        nm_rotate_local(cx-hx,cy+hy,cz+hz),
    };
    static const int faces[6][4] = {
        {0,1,2,3},{5,4,7,6},{4,0,3,7},
        {1,5,6,2},{3,2,6,7},{4,5,1,0}
    };
    for (int fi=0; fi<6; ++fi) {
        NmVertex q[4];
        float d[4];
        bool ok=true;
        for (int k=0;k<4;++k) {
            if (!nm_project(p[faces[fi][k]],q[k],r,g,b,1.0f,&d[k])) {
                ok=false;
                break;
            }
        }
        if (!ok) continue;
        NmFace face{};
        face.v[0]=q[0]; face.v[1]=q[1]; face.v[2]=q[2];
        face.v[3]=q[0]; face.v[4]=q[2]; face.v[5]=q[3];
        face.depth=(d[0]+d[1]+d[2]+d[3])*0.25f;
        nm_faces.push_back(face);
    }
}

static void nm_build_steve() {
    nm_faces.clear();
    // Minecraft-like proportions in SM64 world units.
    nm_add_box(0,156,0,50,50,50, 0.72f,0.52f,0.36f); // head
    nm_add_box(0,111,0,60,70,30, 0.05f,0.55f,0.62f); // shirt
    nm_add_box(-18,48,0,27,90,28, 0.12f,0.20f,0.55f);
    nm_add_box( 18,48,0,27,90,28, 0.12f,0.20f,0.55f);
    nm_add_box(-44,108,0,24,74,24, 0.72f,0.52f,0.36f);
    nm_add_box( 44,108,0,24,74,24, 0.72f,0.52f,0.36f);

    std::sort(nm_faces.begin(), nm_faces.end(),
        [](const NmFace &a, const NmFace &b) { return a.depth > b.depth; });
    for (const NmFace &f : nm_faces) {
        for (int i=0;i<6;++i) nm_vertices.push_back(f.v[i]);
    }
}

static void nm_build_hud() {
    const float w=(float)d3d.current_width, h=(float)d3d.current_height;
    const float slot=42.0f;
    const float total=slot*9.0f;
    const float x0=(w-total)*0.5f;
    const float y=h-slot-18.0f;

    for (int i=0;i<9;++i) {
        const float x=x0+i*slot;
        const bool selected=i==nm_slot;
        nm_push_rect_px(x,y,slot-2,slot-2,
            selected?0.88f:0.18f,
            selected?0.88f:0.18f,
            selected?0.88f:0.18f,
            0.82f);
        nm_push_rect_px(x+4,y+4,slot-10,slot-10,
            0.16f + 0.055f*i,
            0.42f,
            0.18f + 0.035f*(8-i),
            0.95f);
    }

    // crosshair
    nm_push_rect_px(w*0.5f-1.0f,h*0.5f-8.0f,2.0f,16.0f,1,1,1,0.95f);
    nm_push_rect_px(w*0.5f-8.0f,h*0.5f-1.0f,16.0f,2.0f,1,1,1,0.95f);

    if (nm_first_person) {
        // blocky first-person Steve arm
        nm_push_rect_ndc(0.48f,-1.02f,0.98f,-0.40f,0.72f,0.52f,0.36f,1.0f);
        nm_push_rect_ndc(0.55f,-0.80f,0.91f,-0.48f,0.05f,0.55f,0.62f,1.0f);
    }
}

static bool nm_init_pipeline() {
    if (nm_pipeline_ready) return true;

    static const char *shader = R"(
struct VSIn { float3 p:POSITION; float4 c:COLOR0; };
struct VSOut { float4 p:SV_POSITION; float4 c:COLOR0; };
VSOut VS(VSIn i) { VSOut o; o.p=float4(i.p,1); o.c=i.c; return o; }
float4 PS(VSOut i):SV_TARGET { return i.c; }
)";

    ComPtr<ID3DBlob> vsb, psb, err;
    if (FAILED(d3d.D3DCompile(shader,strlen(shader),"NM",nullptr,nullptr,
        "VS","vs_4_0",D3DCOMPILE_OPTIMIZATION_LEVEL2,0,
        vsb.GetAddressOf(),err.GetAddressOf()))) return false;
    err.Reset();
    if (FAILED(d3d.D3DCompile(shader,strlen(shader),"NM",nullptr,nullptr,
        "PS","ps_4_0",D3DCOMPILE_OPTIMIZATION_LEVEL2,0,
        psb.GetAddressOf(),err.GetAddressOf()))) return false;

    if (FAILED(d3d.device->CreateVertexShader(
        vsb->GetBufferPointer(),vsb->GetBufferSize(),nullptr,nm_vs.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreatePixelShader(
        psb->GetBufferPointer(),psb->GetBufferSize(),nullptr,nm_ps.GetAddressOf()))) return false;

    D3D11_INPUT_ELEMENT_DESC desc[] = {
        {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"COLOR",0,DXGI_FORMAT_R32G32B32A32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
    };
    if (FAILED(d3d.device->CreateInputLayout(
        desc,2,vsb->GetBufferPointer(),vsb->GetBufferSize(),nm_layout.GetAddressOf()))) return false;

    D3D11_BUFFER_DESC bd{};
    bd.ByteWidth=sizeof(NmVertex)*16384;
    bd.Usage=D3D11_USAGE_DYNAMIC;
    bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;
    bd.CPUAccessFlags=D3D11_CPU_ACCESS_WRITE;
    if (FAILED(d3d.device->CreateBuffer(&bd,nullptr,nm_vb.GetAddressOf()))) return false;

    D3D11_BLEND_DESC blend{};
    blend.RenderTarget[0].BlendEnable=TRUE;
    blend.RenderTarget[0].SrcBlend=D3D11_BLEND_SRC_ALPHA;
    blend.RenderTarget[0].DestBlend=D3D11_BLEND_INV_SRC_ALPHA;
    blend.RenderTarget[0].BlendOp=D3D11_BLEND_OP_ADD;
    blend.RenderTarget[0].SrcBlendAlpha=D3D11_BLEND_ONE;
    blend.RenderTarget[0].DestBlendAlpha=D3D11_BLEND_INV_SRC_ALPHA;
    blend.RenderTarget[0].BlendOpAlpha=D3D11_BLEND_OP_ADD;
    blend.RenderTarget[0].RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;
    if (FAILED(d3d.device->CreateBlendState(&blend,nm_blend.GetAddressOf()))) return false;

    D3D11_DEPTH_STENCIL_DESC dd{};
    dd.DepthEnable=FALSE;
    dd.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO;
    dd.DepthFunc=D3D11_COMPARISON_ALWAYS;
    if (FAILED(d3d.device->CreateDepthStencilState(&dd,nm_no_depth.GetAddressOf()))) return false;

    nm_pipeline_ready=true;
    return true;
}

static void nm_render_native_minecraft() {
    if (!native_minecraft_active() || !nm_init_pipeline()) return;

    native_minecraft_get_render_state(
        &nm_px,&nm_py,&nm_pz,&nm_yaw,&nm_pitch,&nm_first_person,&nm_slot
    );

    nm_vertices.clear();
    nm_vertices.reserve(4096);

    if (!nm_first_person) nm_build_steve();
    nm_build_hud();
    if (nm_vertices.empty()) return;

    D3D11_MAPPED_SUBRESOURCE mapped{};
    if (FAILED(d3d.context->Map(nm_vb.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped))) return;
    const size_t bytes=nm_vertices.size()*sizeof(NmVertex);
    if (bytes > sizeof(NmVertex)*16384) {
        d3d.context->Unmap(nm_vb.Get(),0);
        return;
    }
    memcpy(mapped.pData,nm_vertices.data(),bytes);
    d3d.context->Unmap(nm_vb.Get(),0);

    UINT stride=sizeof(NmVertex), offset=0;
    ID3D11Buffer *buffer=nm_vb.Get();
    d3d.context->OMSetRenderTargets(1,d3d.backbuffer_view.GetAddressOf(),nullptr);
    d3d.context->OMSetBlendState(nm_blend.Get(),nullptr,0xFFFFFFFF);
    d3d.context->OMSetDepthStencilState(nm_no_depth.Get(),0);
    d3d.context->IASetInputLayout(nm_layout.Get());
    d3d.context->IASetVertexBuffers(0,1,&buffer,&stride,&offset);
    d3d.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    d3d.context->VSSetShader(nm_vs.Get(),nullptr,0);
    d3d.context->PSSetShader(nm_ps.Get(),nullptr,0);
    d3d.context->Draw((UINT)nm_vertices.size(),0);

    // Our direct D3D state changes bypass SM64's state cache.
    d3d.last_shader_program=nullptr;
    d3d.last_vertex_buffer_stride=0;
    d3d.last_blend_state.Reset();
    d3d.last_depth_test=-1;
    d3d.last_depth_mask=-1;
    d3d.last_zmode_decal=-1;
    d3d.last_primitive_topology=D3D_PRIMITIVE_TOPOLOGY_UNDEFINED;
}
''', encoding="utf-8")

# Inject the native visual layer into SM64's D3D11 end-of-frame path.
gfx = GFX / "gfx_direct3d11.cpp"
patch_once(
    gfx,
    "#include <cstdio>\n#include <vector>\n#include <cmath>\n",
    "#include <cstdio>\n#include <vector>\n#include <cmath>\n#include <algorithm>\n#include <cstring>\n"
    '#include "native_minecraft/native_minecraft.h"\n',
)
patch_once(
    gfx,
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
    '#include "native_minecraft_render.inc"\n\n'
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
)
patch_once(
    gfx,
    "static void gfx_d3d11_end_frame(void) {\n}\n",
    "static void gfx_d3d11_end_frame(void) {\n"
    "    nm_render_native_minecraft();\n"
    "}\n",
)

# Native movement owns Mario's visible/gameplay pose each game tick.
mario = SM64 / "src" / "game" / "mario.c"
patch_once(
    mario,
    '#include "rumble_init.h"\n',
    '#include "rumble_init.h"\n#include "pc/native_minecraft/native_minecraft.h"\n',
)
patch_once(
    mario,
    "        update_mario_health(gMarioState);\n"
    "        update_mario_info_for_cam(gMarioState);\n",
    "        update_mario_health(gMarioState);\n"
    "        native_minecraft_tick(gMarioState);\n"
    "        update_mario_info_for_cam(gMarioState);\n",
)
patch_once(
    mario,
    "        mario_update_hitbox_and_cap_model(gMarioState);\n",
    "        mario_update_hitbox_and_cap_model(gMarioState);\n"
    "        if (native_minecraft_active()) {\n"
    "            gMarioState->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;\n"
    "        }\n",
)

# Minecraft mouse look becomes the real SM64 camera.
camera = SM64 / "src" / "game" / "camera.c"
patch_once(
    camera,
    '#include "level_table.h"\n',
    '#include "level_table.h"\n#include "pc/native_minecraft/native_minecraft.h"\n',
)
patch_once(
    camera,
    "    update_lakitu(c);\n\n"
    "    gLakituState.lastFrameAction = sMarioCamState->action;\n",
    "    update_lakitu(c);\n"
    "    native_minecraft_override_camera();\n\n"
    "    gLakituState.lastFrameAction = sMarioCamState->action;\n",
)

# Hide duplicate Mario HUD. A native Minecraft HUD renderer is added separately.
hud = SM64 / "src" / "game" / "hud.c"
patch_once(
    hud,
    '#include "hud.h"\n',
    '#include "hud.h"\n#include "pc/native_minecraft/native_minecraft.h"\n',
)
patch_once(
    hud,
    "void render_hud(void) {\n"
    "    s16 hudDisplayFlags;\n",
    "void render_hud(void) {\n"
    "    if (native_minecraft_active()) {\n"
    "        return;\n"
    "    }\n"
    "    s16 hudDisplayFlags;\n",
)

print("Generated one-process Native Minecraft runtime in:", NM)
print("No Java/Fabric/WebSocket/shared-memory guest is used.")
