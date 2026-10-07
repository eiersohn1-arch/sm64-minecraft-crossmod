#include "native_minecraft_internal.h"

#include <cmath>

extern "C" {
#include "sm64.h"
#include "engine/math_util.h"
#include "engine/surface_collision.h"
#include "game/area.h"
#include "game/camera.h"
#include "game/level_update.h"
#include "game/mario.h"
#include "game/game_init.h"

extern struct CameraFOVStatus sFOVState;
}

namespace {

constexpr float NM_FOV = 70.0f;

bool level_or_area_changed() {
    return !gNm.player.initialized
        || gNm.player.level != gCurrLevelNum
        || gNm.player.area != gCurrAreaIndex;
}

} // namespace

bool nm_should_have_authority(const MarioState *m) {
    if (!m || !m->marioObj || gCurrentArea == nullptr) return false;
    if (gCamera != nullptr && gCamera->cutscene != 0) return false;

    const u32 group = m->action & ACT_GROUP_MASK;
    switch (group) {
        case ACT_GROUP_STATIONARY:
        case ACT_GROUP_MOVING:
        case ACT_GROUP_AIRBORNE:
            return true;

        // Until native swimming/object/cutscene behavior exists, SM64 remains
        // authoritative for these groups. The native player mirrors Mario so
        // control resumes at the correct position afterward.
        case ACT_GROUP_SUBMERGED:
        case ACT_GROUP_CUTSCENE:
        case ACT_GROUP_AUTOMATIC:
        case ACT_GROUP_OBJECT:
        default:
            return false;
    }
}

extern "C" void native_minecraft_pre_mario_action(MarioState *m) {
    if (!m || !m->controller) return;

    gNm.authority = nm_should_have_authority(m);
    if (!gNm.authority) return;

    // Prevent the normal SM64 keyboard map from simultaneously driving Mario
    // while WASD/Space/Ctrl/Shift drive the native Minecraft controller.
    m->controller->rawStickX = 0;
    m->controller->rawStickY = 0;
    m->controller->stickX = 0.0f;
    m->controller->stickY = 0.0f;
    m->controller->stickMag = 0.0f;
    m->controller->buttonDown = 0;
    m->controller->buttonPressed = 0;
}

extern "C" void native_minecraft_tick(MarioState *m) {
    if (!m || !m->marioObj || gCurrentArea == nullptr) return;

    nm_world_load_once();

    if (level_or_area_changed()) {
        nm_sync_player_from_mario(m);
        gNm.authority = false;
        gNm.input.rawMouseX = 0;
        gNm.input.rawMouseY = 0;
        nm_input_end_frame();
        return;
    }

    gNm.authority = nm_should_have_authority(m);

    if (!gNm.authority) {
        nm_sync_player_from_mario(m);
        gNm.input.rawMouseX = 0;
        gNm.input.rawMouseY = 0;
        nm_input_end_frame();
        return;
    }

    nm_input_begin_frame();
    nm_simulate_player();
    nm_world_interact();
    native_minecraft_apply_proxy(m);
    nm_input_end_frame();
}

extern "C" void native_minecraft_apply_proxy(MarioState *m) {
    if (!m || !m->marioObj || !gNm.player.initialized) return;

    Surface *floor = nullptr;
    const float floorY = find_floor(
        gNm.player.x,
        gNm.player.y + NM_PLAYER_HEIGHT + 120.0f,
        gNm.player.z,
        &floor
    );

    // SM64 internals assume Mario has a valid floor pointer in many actions.
    // Never write a proxy pose that would violate that invariant.
    if (floor == nullptr || floorY <= FLOOR_LOWER_LIMIT) {
        return;
    }

    constexpr float ANGLE = 65536.0f / 360.0f;
    const float sm64Yaw = 180.0f - gNm.player.yaw;

    m->pos[0] = gNm.player.x;
    m->pos[1] = gNm.player.y;
    m->pos[2] = gNm.player.z;

    m->vel[0] = gNm.player.vx;
    m->vel[1] = gNm.player.vy;
    m->vel[2] = gNm.player.vz;
    m->forwardVel = std::sqrt(
        gNm.player.vx * gNm.player.vx
        + gNm.player.vz * gNm.player.vz
    );

    m->faceAngle[0] = 0;
    m->faceAngle[1] = (s16)(sm64Yaw * ANGLE);
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
    m->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;
}

extern "C" void native_minecraft_override_camera(void) {
    if (!gNm.authority || !gNm.player.initialized || gCamera == nullptr) return;

    const float yaw = gNm.player.yaw * 0.01745329251994329577f;
    const float pitch = gNm.player.pitch * 0.01745329251994329577f;
    const float cp = std::cos(pitch);

    const float fx = -std::sin(yaw) * cp;
    const float fy = -std::sin(pitch);
    const float fz = -std::cos(yaw) * cp;

    const float eyeX = gNm.player.x;
    const float eyeY = gNm.player.y + NM_EYE_HEIGHT;
    const float eyeZ = gNm.player.z;
    const float distance = gNm.player.firstPerson ? 0.0f : 400.0f;

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
    sFOVState.fov = NM_FOV;
    sFOVState.fovOffset = 0.0f;
}

extern "C" int native_minecraft_active(void) {
    return gNm.player.initialized ? 1 : 0;
}

extern "C" int native_minecraft_has_authority(void) {
    return gNm.authority ? 1 : 0;
}

extern "C" int native_minecraft_first_person(void) {
    return gNm.player.firstPerson ? 1 : 0;
}

extern "C" int native_minecraft_selected_slot(void) {
    return gNm.player.selectedSlot;
}

extern "C" void native_minecraft_get_render_state(
    float *x, float *y, float *z,
    float *yaw, float *pitch,
    int *firstPerson, int *selectedSlot, int *inventoryOpen
) {
    if (x) *x = gNm.player.x;
    if (y) *y = gNm.player.y;
    if (z) *z = gNm.player.z;
    if (yaw) *yaw = gNm.player.yaw;
    if (pitch) *pitch = gNm.player.pitch;
    if (firstPerson) *firstPerson = gNm.player.firstPerson ? 1 : 0;
    if (selectedSlot) *selectedSlot = gNm.player.selectedSlot;
    if (inventoryOpen) *inventoryOpen = gNm.player.inventoryOpen ? 1 : 0;
}
