#!/usr/bin/env python3
"""Generate a one-process Minecraft-like runtime directly inside sm64-port.

Universal Modder mashup Pattern 4: reimplement, then fuse.
No Fabric guest, WebSocket, shared memory or second game process is used.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SM64 = ROOT / "vendor" / "sm64-port"
PC = SM64 / "src" / "pc"
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

#ifdef __cplusplus
}
#endif
''', encoding="utf-8")

(NM / "native_minecraft.cpp").write_text(r'''#include "native_minecraft.h"

#include <algorithm>
#include <cmath>
#include <cstdint>

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
        gPlayer.vy = std::max(gPlayer.vy - GRAVITY, -MAX_FALL);
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
