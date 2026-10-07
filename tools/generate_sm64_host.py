#!/usr/bin/env python3
"""Generate the first real SM64 host for Universal Modder's passthrough guest.

Clean-room adapter: transport and protocol come from Universal Modder's
minecraft-gta5-passthrough example. No legacy crossmod source is reused.
Milestone 1 intentionally follows UM's "start small" rule:
SM64 camera/player -> Minecraft, SM64 ground -> Minecraft barriers, host input
-> Minecraft item actions, and MCPT world+HUD -> SM64's D3D11 backbuffer.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
UM = ROOT / "vendor" / "universal-modder"
SM64 = ROOT / "vendor" / "sm64-port"
REF = UM / "examples" / "minecraft-gta5-passthrough" / "gta" / "src"
PC = SM64 / "src" / "pc"
GFX = PC / "gfx"

def patch_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch marker missing in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

if not (SM64 / "src" / "game" / "game_init.c").is_file():
    raise SystemExit("Run setup-windows.bat first.")

# Universal Modder's transport is copied verbatim.
for name in ("ws.cpp", "ws.h"):
    shutil.copy2(REF / name, PC / name)

(PC / "sm64_passthrough.h").write_text(r'''#pragma once
#ifdef __cplusplus
extern "C" {
#endif
struct MarioState;
void um_passthrough_start(void);
void um_passthrough_stop(void);
int um_passthrough_connected(void);
int um_passthrough_minecraft_authority(void);
void um_passthrough_apply_mario_proxy(struct MarioState *m);
void um_passthrough_override_camera(void);
void um_passthrough_before_frame(void);
void um_passthrough_frame(void);
#ifdef __cplusplus
}
#endif
''', encoding="utf-8")

(PC / "sm64_passthrough.cpp").write_text(r'''#include "sm64_passthrough.h"
#include "ws.h"
#include <cmath>
#include <cstdio>
#include <string>
#include <unordered_set>

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
#include "engine/surface_collision.h"
#include "engine/math_util.h"
#include "game/area.h"
#include "game/camera.h"
#include "game/level_update.h"
#include "game/mario.h"
}

static WsClient s_ws;
static unsigned long long s_frame = 0;
static int s_generation = -1;
static int s_level = -1;
static int s_area = -1;
static std::unordered_set<unsigned long long> s_ground_sampled;
static bool s_attack, s_use, s_inventory, s_drop, s_swap, s_escape;
static bool s_slots[9] = {};
static bool s_first_person = false;
static bool s_spawn_sync_pending = false;
static int s_drive_delay_frames = 0;

struct McPose {
    bool valid = false;
    double x = 0.0, y = 64.0, z = 0.0;
    double vx = 0.0, vy = 0.0, vz = 0.0;
    float yaw = 0.0f, pitch = 0.0f;
};
static McPose s_mc;

static bool host_has_focus() {
    HWND hwnd = GetForegroundWindow();
    if (!hwnd) return false;
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    return pid == GetCurrentProcessId();
}

static bool down(int vk) {
    return host_has_focus() && (GetAsyncKeyState(vk) & 0x8000) != 0;
}

static bool native_sm64_action_owns_player() {
    if (gMarioState == nullptr) return true;
    const u32 group = gMarioState->action & ACT_GROUP_MASK;
    return group == ACT_GROUP_CUTSCENE
        || group == ACT_GROUP_AUTOMATIC
        || group == ACT_GROUP_OBJECT;
}

static void poll_guest_messages() {
    std::string message;
    while (s_ws.poll(message)) {
        McPose pose;
        int matched = std::sscanf(
            message.c_str(),
            "{\"t\":\"mcpos\",\"pos\":[%lf,%lf,%lf],"
            "\"vel\":[%lf,%lf,%lf],\"r\":[%f,%f]",
            &pose.x, &pose.y, &pose.z,
            &pose.vx, &pose.vy, &pose.vz,
            &pose.yaw, &pose.pitch
        );
        if (matched == 8) {
            pose.valid = true;
            s_mc = pose;
        }
    }
}

static void send_key(const char *name, int vk, bool &previous) {
    if (!host_has_focus()) {
        if (previous) {
            previous = false;
            char up[96];
            std::snprintf(up, sizeof(up),
                "{\"t\":\"key\",\"k\":\"%s\",\"down\":false}", name);
            s_ws.send(up);
        }
        return;
    }

    const SHORT state = GetAsyncKeyState(vk);
    const bool now = (state & 0x8000) != 0;
    const bool pressedSincePoll = (state & 0x0001) != 0;

    if (now != previous) {
        previous = now;
        char msg[96];
        std::snprintf(msg, sizeof(msg),
            "{\"t\":\"key\",\"k\":\"%s\",\"down\":%s}",
            name, now ? "true" : "false");
        s_ws.send(msg);
        return;
    }

    // SM64 updates at 30 Hz. A quick mouse click can begin and end between
    // two frames. Windows preserves that edge in GetAsyncKeyState's low bit,
    // so synthesize a short press instead of losing the Minecraft action.
    if (pressedSincePoll && !now) {
        char msg[96];
        std::snprintf(msg, sizeof(msg),
            "{\"t\":\"key\",\"k\":\"%s\",\"down\":true}", name);
        s_ws.send(msg);
        std::snprintf(msg, sizeof(msg),
            "{\"t\":\"key\",\"k\":\"%s\",\"down\":false}", name);
        s_ws.send(msg);
    }
}

static void publish_input() {
    send_key("attack", VK_LBUTTON, s_attack);
    send_key("use", VK_RBUTTON, s_use);
    send_key("inventory", 'E', s_inventory);
    send_key("drop", 'Q', s_drop);
    send_key("swap", 'F', s_swap);
    send_key("escape", VK_ESCAPE, s_escape);

    for (int i = 0; i < 9; ++i) {
        bool now = down('1' + i);
        if (now && !s_slots[i]) {
            char msg[48];
            std::snprintf(msg, sizeof(msg), "{\"t\":\"slot\",\"n\":%d}", i);
            s_ws.send(msg);
        }
        s_slots[i] = now;
    }

    const bool forward = down('W');
    const bool back = down('S');
    const bool left = down('A');
    const bool right = down('D');
    const bool jump = down(VK_SPACE);
    const bool sneak = down(VK_SHIFT);
    const bool sprint = down(VK_CONTROL);

    char movement[192];
    std::snprintf(
        movement, sizeof(movement),
        "{\"t\":\"move\",\"f\":%s,\"b\":%s,\"l\":%s,\"r\":%s,"
        "\"jump\":%s,\"sneak\":%s,\"sprint\":%s}",
        forward ? "true" : "false",
        back ? "true" : "false",
        left ? "true" : "false",
        right ? "true" : "false",
        jump ? "true" : "false",
        sneak ? "true" : "false",
        sprint ? "true" : "false"
    );
    s_ws.send(movement);

    if (host_has_focus()) {
        HWND hwnd = GetForegroundWindow();
        RECT rect{};
        if (hwnd && GetClientRect(hwnd, &rect)) {
            POINT center{
                (rect.right - rect.left) / 2,
                (rect.bottom - rect.top) / 2
            };
            POINT screenCenter = center;
            ClientToScreen(hwnd, &screenCenter);

            POINT cursor{};
            if (GetCursorPos(&cursor)) {
                const int dx = cursor.x - screenCenter.x;
                const int dy = cursor.y - screenCenter.y;
                if (dx != 0 || dy != 0) {
                    char look[128];
                    std::snprintf(
                        look, sizeof(look),
                        "{\"t\":\"look\",\"dx\":%d,\"dy\":%d}",
                        dx, dy
                    );
                    s_ws.send(look);
                }
                SetCursorPos(screenCenter.x, screenCenter.y);
            }
        }
    }

    if (host_has_focus() && (GetAsyncKeyState(VK_F5) & 0x0001)) {
        s_first_person = !s_first_person;
    }
}

static unsigned long long column_key(int x, int z) {
    return (static_cast<unsigned long long>(
        static_cast<unsigned int>(x)) << 32)
        | static_cast<unsigned int>(z);
}

static void reset_ground_if_needed() {
    int generation = s_ws.generation();
    if (generation == s_generation
        && gCurrLevelNum == s_level
        && gCurrAreaIndex == s_area) return;

    s_generation = generation;
    s_level = gCurrLevelNum;
    s_area = gCurrAreaIndex;
    s_ground_sampled.clear();
    s_mc.valid = false;
    s_spawn_sync_pending = true;
    s_drive_delay_frames = 6;
    s_ws.send("{\"t\":\"clear\"}");
}

static void publish_ground() {
    if (!gMarioState) return;
    constexpr float SCALE = 100.0f;
    constexpr float Y0 = 64.0f;
    constexpr int RADIUS = 14;
    constexpr int BUDGET = 100;

    int cx = static_cast<int>(std::floor(gMarioState->pos[0] / SCALE));
    int cz = static_cast<int>(std::floor(-gMarioState->pos[2] / SCALE));
    std::string cols;
    int probes = 0;

    for (int dz = -RADIUS; dz <= RADIUS && probes < BUDGET; ++dz) {
        for (int dx = -RADIUS; dx <= RADIUS && probes < BUDGET; ++dx) {
            if (dx * dx + dz * dz > RADIUS * RADIUS) continue;
            int x = cx + dx, z = cz + dz;
            auto key = column_key(x, z);
            if (s_ground_sampled.count(key)) continue;
            ++probes;

            struct Surface *surface = nullptr;
            float floor_y = find_floor(
                (x + 0.5f) * SCALE,
                gMarioState->pos[1] + 500.0f,
                -(z + 0.5f) * SCALE,
                &surface
            );
            if (!surface) continue;

            s_ground_sampled.insert(key);
            int top = static_cast<int>(
                std::floor(floor_y / SCALE + Y0 + 0.5f)) - 1;
            char entry[72];
            std::snprintf(entry, sizeof(entry), "%s%d,%d,%d,%d",
                cols.empty() ? "" : ",", x, z, top - 2, top);
            cols += entry;
        }
    }

    if (!cols.empty()) {
        s_ws.send("{\"t\":\"ground\",\"c\":[" + cols + "]}");

        if (s_spawn_sync_pending) {
            const double x = gMarioState->pos[0] / SCALE;
            const double y = gMarioState->pos[1] / SCALE + Y0 + 0.10;
            const double z = -gMarioState->pos[2] / SCALE;
            char command[160];
            std::snprintf(
                command, sizeof(command),
                "{\"t\":\"cmd\",\"c\":\"tp @a %.4f %.4f %.4f\"}",
                x, y, z
            );
            s_ws.send(command);
            s_ws.send("{\"t\":\"cmd\",\"c\":\"gamemode survival @a\"}");
            s_spawn_sync_pending = false;
        }
    }
}

void um_passthrough_start(void) {
    s_ws.start("127.0.0.1", 25599);
}

void um_passthrough_stop(void) {
    s_ws.stop();
}

int um_passthrough_connected(void) {
    return s_ws.connected() ? 1 : 0;
}

int um_passthrough_minecraft_authority(void) {
    return s_ws.connected()
        && s_mc.valid
        && !native_sm64_action_owns_player();
}

void um_passthrough_apply_mario_proxy(struct MarioState *m) {
    if (!m || !m->marioObj || !um_passthrough_minecraft_authority()) return;

    constexpr float SCALE = 100.0f;
    constexpr float Y0 = 64.0f;
    constexpr float ANGLE = 65536.0f / 360.0f;

    m->pos[0] = static_cast<float>(s_mc.x * SCALE);
    m->pos[1] = static_cast<float>((s_mc.y - Y0) * SCALE);
    m->pos[2] = static_cast<float>(-s_mc.z * SCALE);

    m->vel[0] = static_cast<float>(s_mc.vx * SCALE);
    m->vel[1] = static_cast<float>(s_mc.vy * SCALE);
    m->vel[2] = static_cast<float>(-s_mc.vz * SCALE);
    m->forwardVel = static_cast<float>(
        std::sqrt(s_mc.vx * s_mc.vx + s_mc.vz * s_mc.vz) * SCALE
    );

    const float sm64Yaw = 180.0f - s_mc.yaw;
    m->faceAngle[0] = 0;
    m->faceAngle[1] = static_cast<s16>(sm64Yaw * ANGLE);
    m->faceAngle[2] = 0;

    m->marioObj->oPosX = m->pos[0];
    m->marioObj->oPosY = m->pos[1];
    m->marioObj->oPosZ = m->pos[2];
    m->marioObj->header.gfx.pos[0] = m->pos[0];
    m->marioObj->header.gfx.pos[1] = m->pos[1];
    m->marioObj->header.gfx.pos[2] = m->pos[2];
    m->marioObj->header.gfx.angle[1] = m->faceAngle[1];
    m->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;

    m->floorHeight = find_floor(
        m->pos[0], m->pos[1] + 180.0f, m->pos[2], &m->floor
    );
}

void um_passthrough_override_camera(void) {
    if (!um_passthrough_minecraft_authority() || gCamera == nullptr) return;

    constexpr float SCALE = 100.0f;
    constexpr float Y0 = 64.0f;
    constexpr float DEG = 0.01745329251994329577f;

    const float yaw = s_mc.yaw * DEG;
    const float pitch = s_mc.pitch * DEG;
    const float cp = std::cos(pitch);

    // Vanilla Minecraft look vector, converted to SM64's flipped Z axis.
    const float fx = -std::sin(yaw) * cp;
    const float fy = -std::sin(pitch);
    const float fz = -std::cos(yaw) * cp;

    const float eyeX = static_cast<float>(s_mc.x * SCALE);
    const float eyeY = static_cast<float>((s_mc.y - Y0 + 1.62) * SCALE);
    const float eyeZ = static_cast<float>(-s_mc.z * SCALE);

    const float distance = s_first_person ? 0.0f : 400.0f;
    Vec3f pos = {
        eyeX - fx * distance,
        eyeY - fy * distance,
        eyeZ - fz * distance
    };
    Vec3f focus = {
        eyeX + fx * 200.0f,
        eyeY + fy * 200.0f,
        eyeZ + fz * 200.0f
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

void um_passthrough_before_frame(void) {
    if (!s_ws.connected()) return;

    poll_guest_messages();

    if (gMarioState && gMarioState->marioObj) {
        if (um_passthrough_minecraft_authority()) {
            um_passthrough_apply_mario_proxy(gMarioState);
        }
        gMarioState->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;
    }
}

void um_passthrough_frame(void) {
    if (!s_ws.connected() || !gMarioState) return;

    reset_ground_if_needed();

    constexpr float SCALE = 100.0f;
    constexpr float Y0 = 64.0f;
    constexpr float RAD_TO_DEG = 57.29577951308232f;

    // Bootstrap without a circular wait: while collision/spawn is being
    // installed Minecraft follows the host.  On the next frame we request
    // drive even before the first mcpos arrives; PlayerSync then reports the
    // real Minecraft pose back and full authority becomes active.
    if (!s_spawn_sync_pending && s_drive_delay_frames > 0) {
        --s_drive_delay_frames;
    }
    const bool drive =
        !native_sm64_action_owns_player()
        && !s_spawn_sync_pending
        && s_drive_delay_frames == 0;

    const float cam_x = gLakituState.curPos[0] / SCALE;
    const float cam_y = gLakituState.curPos[1] / SCALE + Y0;
    const float cam_z = -gLakituState.curPos[2] / SCALE;
    const float player_x = gMarioState->pos[0] / SCALE;
    const float player_y = gMarioState->pos[1] / SCALE + Y0;
    const float player_z = -gMarioState->pos[2] / SCALE;

    const float dx = (gLakituState.curFocus[0] - gLakituState.curPos[0]) / SCALE;
    const float dy = (gLakituState.curFocus[1] - gLakituState.curPos[1]) / SCALE;
    const float dz = -(gLakituState.curFocus[2] - gLakituState.curPos[2]) / SCALE;
    float yaw = std::atan2(-dx, dz) * RAD_TO_DEG;
    float pitch = -std::atan2(
        dy, std::sqrt(dx * dx + dz * dz)) * RAD_TO_DEG;
    float body_yaw = 180.0f
        - static_cast<float>(gMarioState->faceAngle[1])
          * (360.0f / 65536.0f);

    if (drive) {
        yaw = s_mc.yaw;
        pitch = s_mc.pitch;
        body_yaw = s_mc.yaw;
    }

    char msg[640];
    std::snprintf(msg, sizeof(msg),
        "{\"t\":\"cam\",\"f\":%llu,"
        "\"p\":[%.4f,%.4f,%.4f],"
        "\"r\":[%.3f,%.3f,0],\"fov\":70,"
        "\"fp\":%s,\"pl\":[%.4f,%.4f,%.4f],\"h\":%.3f,"
        "\"drive\":%s,\"look\":[%.3f,%.3f]}",
        ++s_frame,
        cam_x, cam_y, cam_z,
        yaw, pitch,
        s_first_person ? "true" : "false",
        player_x, player_y, player_z,
        body_yaw,
        drive ? "true" : "false",
        yaw, pitch
    );
    s_ws.send(msg);

    publish_ground();
    publish_input();
}
''', encoding="utf-8")

# Minimal MCPT compositor. This deliberately omits depth for milestone 1.
# Minecraft's world is transparent where nothing is drawn; HUD/hand is a
# separate premultiplied-alpha layer exactly like Universal Modder's example.
(GFX / "um_mcpt_overlay.inc").write_text(r'''
static constexpr wchar_t UM_MCPT_NAME[] = L"Local\\MCPassthroughFrame";
static constexpr uint32_t UM_MCPT_MAGIC = 0x5450434D;
static constexpr size_t UM_MCPT_HEADER = 4096;
static constexpr size_t UM_MCPT_DESC = 256;
static constexpr size_t UM_MCPT_DESC_BYTES = 128;

struct UmMcpt {
    HANDLE mapping = nullptr;
    const uint8_t *memory = nullptr;
    int slots = 0;
    int64_t stride = 0;
    int64_t last_publish = -1;
    DWORD retry_after = 0;
    uint32_t width = 0, height = 0;
    ComPtr<ID3D11Texture2D> world, overlay;
    ComPtr<ID3D11ShaderResourceView> world_srv, overlay_srv;
    ComPtr<ID3D11VertexShader> vs;
    ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11SamplerState> sampler;
    ComPtr<ID3D11BlendState> blend;
    ComPtr<ID3D11DepthStencilState> no_depth;
    bool ready = false;
};
static UmMcpt um_mcpt;

template<typename T>
static T um_read(const uint8_t *p) {
    T v; std::memcpy(&v, p, sizeof(v)); return v;
}

static bool um_open_mcpt() {
    if (um_mcpt.memory) return true;
    DWORD now = GetTickCount();
    if (now < um_mcpt.retry_after) return false;
    um_mcpt.retry_after = now + 1000;

    um_mcpt.mapping = OpenFileMappingW(FILE_MAP_READ, FALSE, UM_MCPT_NAME);
    if (!um_mcpt.mapping) return false;

    auto header = static_cast<const uint8_t*>(
        MapViewOfFile(um_mcpt.mapping, FILE_MAP_READ, 0, 0, UM_MCPT_HEADER));
    if (!header || um_read<uint32_t>(header) != UM_MCPT_MAGIC) {
        if (header) UnmapViewOfFile(header);
        CloseHandle(um_mcpt.mapping);
        um_mcpt.mapping = nullptr;
        return false;
    }
    um_mcpt.slots = um_read<int32_t>(header + 12);
    um_mcpt.stride = um_read<int64_t>(header + 16);
    UnmapViewOfFile(header);
    if (um_mcpt.slots <= 0 || um_mcpt.stride <= 0) return false;

    SIZE_T bytes = static_cast<SIZE_T>(
        UM_MCPT_HEADER + um_mcpt.stride * um_mcpt.slots);
    um_mcpt.memory = static_cast<const uint8_t*>(
        MapViewOfFile(um_mcpt.mapping, FILE_MAP_READ, 0, 0, bytes));
    return um_mcpt.memory != nullptr;
}

static bool um_pipeline() {
    if (um_mcpt.ready) return true;
    static const char *src = R"(
Texture2D World : register(t0);
Texture2D Overlay : register(t1);
SamplerState Samp : register(s0);
struct O { float4 p:SV_POSITION; float2 uv:TEXCOORD0; };
O VS(uint id:SV_VertexID) {
    O o; float2 u=float2((id<<1)&2,id&2);
    o.p=float4(u*float2(2,-2)+float2(-1,1),0,1); o.uv=u; return o;
}
float4 PS(O i):SV_TARGET {
    float2 uv=float2(i.uv.x,1-i.uv.y);
    float4 w=World.Sample(Samp,uv);
    float4 h=Overlay.Sample(Samp,uv);
    return h + w*(1-h.a);
})";
    ComPtr<ID3DBlob> vb, pb, err;
    if (FAILED(d3d.D3DCompile(src, strlen(src), "UM-SM64", nullptr, nullptr,
            "VS", "vs_4_0", D3DCOMPILE_OPTIMIZATION_LEVEL2, 0,
            vb.GetAddressOf(), err.GetAddressOf()))) return false;
    err.Reset();
    if (FAILED(d3d.D3DCompile(src, strlen(src), "UM-SM64", nullptr, nullptr,
            "PS", "ps_4_0", D3DCOMPILE_OPTIMIZATION_LEVEL2, 0,
            pb.GetAddressOf(), err.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreateVertexShader(
            vb->GetBufferPointer(), vb->GetBufferSize(), nullptr,
            um_mcpt.vs.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreatePixelShader(
            pb->GetBufferPointer(), pb->GetBufferSize(), nullptr,
            um_mcpt.ps.GetAddressOf()))) return false;

    D3D11_SAMPLER_DESC sd = {};
    sd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.MaxLOD = D3D11_FLOAT32_MAX;
    if (FAILED(d3d.device->CreateSamplerState(
            &sd, um_mcpt.sampler.GetAddressOf()))) return false;

    D3D11_BLEND_DESC bd = {};
    bd.RenderTarget[0].BlendEnable = TRUE;
    bd.RenderTarget[0].SrcBlend = D3D11_BLEND_ONE;
    bd.RenderTarget[0].DestBlend = D3D11_BLEND_INV_SRC_ALPHA;
    bd.RenderTarget[0].BlendOp = D3D11_BLEND_OP_ADD;
    bd.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;
    bd.RenderTarget[0].DestBlendAlpha = D3D11_BLEND_INV_SRC_ALPHA;
    bd.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;
    bd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
    if (FAILED(d3d.device->CreateBlendState(
            &bd, um_mcpt.blend.GetAddressOf()))) return false;

    D3D11_DEPTH_STENCIL_DESC dd = {};
    dd.DepthEnable = FALSE;
    dd.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    dd.DepthFunc = D3D11_COMPARISON_ALWAYS;
    if (FAILED(d3d.device->CreateDepthStencilState(
            &dd, um_mcpt.no_depth.GetAddressOf()))) return false;
    um_mcpt.ready = true;
    return true;
}

static bool um_textures(uint32_t w, uint32_t h) {
    if (um_mcpt.width == w && um_mcpt.height == h &&
        um_mcpt.world.Get() != nullptr &&
        um_mcpt.overlay.Get() != nullptr) return true;
    um_mcpt.world_srv.Reset(); um_mcpt.overlay_srv.Reset();
    um_mcpt.world.Reset(); um_mcpt.overlay.Reset();

    D3D11_TEXTURE2D_DESC td = {};
    td.Width=w; td.Height=h; td.MipLevels=1; td.ArraySize=1;
    td.Format=DXGI_FORMAT_R8G8B8A8_UNORM; td.SampleDesc.Count=1;
    td.Usage=D3D11_USAGE_DEFAULT; td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    if (FAILED(d3d.device->CreateTexture2D(
            &td,nullptr,um_mcpt.world.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreateTexture2D(
            &td,nullptr,um_mcpt.overlay.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreateShaderResourceView(
            um_mcpt.world.Get(),nullptr,um_mcpt.world_srv.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreateShaderResourceView(
            um_mcpt.overlay.Get(),nullptr,um_mcpt.overlay_srv.GetAddressOf()))) return false;
    um_mcpt.width=w; um_mcpt.height=h; return true;
}

static void um_invalidate_sm64_state() {
    d3d.last_shader_program = nullptr;
    d3d.last_vertex_buffer_stride = 0;
    d3d.last_blend_state.Reset();
    d3d.last_resource_views[0].Reset();
    d3d.last_resource_views[1].Reset();
    d3d.last_sampler_states[0].Reset();
    d3d.last_sampler_states[1].Reset();
    d3d.last_depth_test = -1;
    d3d.last_depth_mask = -1;
    d3d.last_zmode_decal = -1;
    d3d.last_primitive_topology = D3D_PRIMITIVE_TOPOLOGY_UNDEFINED;
}

static void um_draw_mcpt() {
    if (!um_open_mcpt() || !um_pipeline()) return;
    int64_t published = um_read<int64_t>(um_mcpt.memory + 32);
    int32_t slot = um_read<int32_t>(um_mcpt.memory + 40);
    if (slot < 0 || slot >= um_mcpt.slots) return;
    const uint8_t *desc = um_mcpt.memory + UM_MCPT_DESC
        + UM_MCPT_DESC_BYTES * slot;
    int64_t seq = um_read<int64_t>(desc);
    if (seq & 1) return;
    uint32_t w=um_read<uint32_t>(desc+24), h=um_read<uint32_t>(desc+28);
    if (!w || !h || w>3840 || h>2160) return;

    if (published != um_mcpt.last_publish) {
        if (!um_textures(w,h)) return;
        const uint8_t *base = um_mcpt.memory + UM_MCPT_HEADER
            + um_mcpt.stride * slot;
        size_t layer = static_cast<size_t>(w)*h*4;
        d3d.context->UpdateSubresource(
            um_mcpt.world.Get(),0,nullptr,base,w*4,0);
        d3d.context->UpdateSubresource(
            um_mcpt.overlay.Get(),0,nullptr,base+2*layer,w*4,0);
        if (um_read<int64_t>(desc) != seq) return;
        um_mcpt.last_publish = published;
    }

    ID3D11ShaderResourceView *views[] = {
        um_mcpt.world_srv.Get(), um_mcpt.overlay_srv.Get()
    };
    ID3D11SamplerState *samps[] = { um_mcpt.sampler.Get() };
    D3D11_VIEWPORT vp = {};
    vp.Width=static_cast<float>(d3d.current_width);
    vp.Height=static_cast<float>(d3d.current_height);
    vp.MinDepth=0; vp.MaxDepth=1;
    d3d.context->RSSetViewports(1,&vp);
    d3d.context->OMSetRenderTargets(
        1,d3d.backbuffer_view.GetAddressOf(),nullptr);
    d3d.context->OMSetBlendState(
        um_mcpt.blend.Get(),nullptr,0xFFFFFFFF);
    d3d.context->OMSetDepthStencilState(um_mcpt.no_depth.Get(),0);
    d3d.context->IASetInputLayout(nullptr);
    d3d.context->IASetPrimitiveTopology(
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    d3d.context->VSSetShader(um_mcpt.vs.Get(),nullptr,0);
    d3d.context->PSSetShader(um_mcpt.ps.Get(),nullptr,0);
    d3d.context->PSSetShaderResources(0,2,views);
    d3d.context->PSSetSamplers(0,1,samps);
    d3d.context->Draw(3,0);
    ID3D11ShaderResourceView *nulls[] = {nullptr,nullptr};
    d3d.context->PSSetShaderResources(0,2,nulls);
    um_invalidate_sm64_state();
}
''', encoding="utf-8")

# Keep native Mario hidden after his own cap/model update.  The pre-frame
# flag alone is not enough because mario_update_hitbox_and_cap_model() can
# rewrite render flags later in the same frame.
mario = SM64 / "src" / "game" / "mario.c"
patch_once(mario, '#include "rumble_init.h"\n',
    '#include "rumble_init.h"\n#include "pc/sm64_passthrough.h"\n')
patch_once(mario,
    "        update_mario_health(gMarioState);\n"
    "        update_mario_info_for_cam(gMarioState);\n",
    "        update_mario_health(gMarioState);\n"
    "        if (um_passthrough_minecraft_authority()) {\n"
    "            um_passthrough_apply_mario_proxy(gMarioState);\n"
    "        }\n"
    "        update_mario_info_for_cam(gMarioState);\n")

patch_once(mario,
    "        mario_update_hitbox_and_cap_model(gMarioState);\n",
    "        mario_update_hitbox_and_cap_model(gMarioState);\n"
    "        if (um_passthrough_connected()) {\n"
    "            gMarioState->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;\n"
    "        }\n")

# While the passthrough is attached, Minecraft owns the visible survival
# HUD. Keep SM64 progression alive internally, but do not draw the duplicate
# lives/stars/camera meter over Minecraft hearts/hunger/hotbar.
hud = SM64 / "src" / "game" / "hud.c"
patch_once(hud, '#include "hud.h"\n',
    '#include "hud.h"\n#include "pc/sm64_passthrough.h"\n')
patch_once(hud,
    "void render_hud(void) {\n"
    "    s16 hudDisplayFlags;\n",
    "void render_hud(void) {\n"
    "    if (um_passthrough_connected()) {\n"
    "        return;\n"
    "    }\n"
    "    s16 hudDisplayFlags;\n")

# When Minecraft owns locomotion, override Lakitu after native SM64 camera
# processing.  This keeps SM64's rendered world and Minecraft's camera on the
# same yaw/pitch instead of letting Lakitu drift independently.
camera = SM64 / "src" / "game" / "camera.c"
patch_once(camera, '#include "level_table.h"\n',
    '#include "level_table.h"\n#include "pc/sm64_passthrough.h"\n')
patch_once(camera,
    "    update_lakitu(c);\n\n"
    "    gLakituState.lastFrameAction = sMarioCamState->action;\n",
    "    update_lakitu(c);\n"
    "    um_passthrough_override_camera();\n\n"
    "    gLakituState.lastFrameAction = sMarioCamState->action;\n")

# Lifecycle hook in the real host.
pc_main = PC / "pc_main.c"
patch_once(pc_main, '#include "configfile.h"\n',
    '#include "configfile.h"\n#include "sm64_passthrough.h"\n')
patch_once(pc_main,
    "    gfx_start_frame();\n    game_loop_one_iteration();\n",
    "    gfx_start_frame();\n    um_passthrough_before_frame();\n"
    "    game_loop_one_iteration();\n    um_passthrough_frame();\n")
patch_once(pc_main,
    '    gfx_init(wm_api, rendering_api, "Super Mario 64 PC-Port", configFullscreen);\n',
    '    gfx_init(wm_api, rendering_api, "Super Mario 64 PC-Port", configFullscreen);\n'
    '    um_passthrough_start();\n    atexit(um_passthrough_stop);\n')

# Draw the latest MCPT world+overlay after SM64 finished its frame.
gfx = GFX / "gfx_direct3d11.cpp"
patch_once(gfx, "#include <cstdio>\n",
    "#include <cstdio>\n#include <cstring>\n")
patch_once(gfx,
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n"
    '#include "um_mcpt_overlay.inc"\n')
patch_once(gfx,
    "static void gfx_d3d11_end_frame(void) {\n}\n",
    "static void gfx_d3d11_end_frame(void) {\n    um_draw_mcpt();\n}\n")

# Universal Modder's ws.cpp uses Winsock and std::thread.
makefile = SM64 / "Makefile"
patch_once(makefile,
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -no-pie -mwindows",
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -pthread -no-pie -mwindows")

print("Clean SM64 Universal Modder host installed into:", SM64)
print("Milestone: real SM64 pose/ground/input + MCPT world/HUD compositor")
