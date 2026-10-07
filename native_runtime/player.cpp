#include "native_minecraft_internal.h"

#include <cmath>

#define WIN32_LEAN_AND_MEAN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

extern "C" {
#include "sm64.h"
#include "engine/surface_collision.h"
#include "game/area.h"
#include "game/level_update.h"
#include "game/mario.h"
}

namespace {

constexpr float WALK_SPEED = 14.3f;
constexpr float SPRINT_SPEED = 18.3f;
constexpr float SNEAK_SPEED = 4.3f;
constexpr float AIR_ACCEL = 2.0f;
constexpr float GROUND_ACCEL = 6.5f;
constexpr float GRAVITY = 5.35f;
constexpr float JUMP_VELOCITY = 28.0f;
constexpr float MAX_FALL = 78.0f;
constexpr float STEP_HEIGHT = 60.0f;

float nm_radians(float degrees) {
    return degrees * 0.01745329251994329577f;
}

void resolve_sm64_walls(float &x, float &y, float &z) {
    WallCollisionData walls{};
    walls.x = x;
    walls.y = y;
    walls.z = z;
    walls.offsetY = NM_PLAYER_HEIGHT * 0.5f;
    walls.radius = NM_PLAYER_RADIUS;
    find_wall_collisions(&walls);
    x = walls.x;
    y = walls.y;
    z = walls.z;
}

void move_axis_with_voxels(float &coord, float candidate, bool xAxis) {
    const float old = coord;
    coord = candidate;

    const float testX = xAxis ? coord : gNm.player.x;
    const float testZ = xAxis ? gNm.player.z : coord;

    if (!nm_world_player_intersects(testX, gNm.player.y, testZ)) {
        return;
    }

    if (gNm.player.onGround
        && !nm_world_player_intersects(
            testX, gNm.player.y + STEP_HEIGHT, testZ)) {
        gNm.player.y += STEP_HEIGHT;
        return;
    }

    coord = old;
    if (xAxis) gNm.player.vx = 0.0f;
    else gNm.player.vz = 0.0f;
}

} // namespace

void nm_sync_player_from_mario(MarioState *m) {
    if (!m) return;

    gNm.player.initialized = true;
    gNm.player.level = gCurrLevelNum;
    gNm.player.area = gCurrAreaIndex;
    gNm.player.x = m->pos[0];
    gNm.player.y = m->pos[1];
    gNm.player.z = m->pos[2];
    gNm.player.vx = 0.0f;
    gNm.player.vy = 0.0f;
    gNm.player.vz = 0.0f;
    gNm.player.yaw =
        180.0f - (float)m->faceAngle[1] * (360.0f / 65536.0f);
    gNm.player.pitch = 0.0f;
    gNm.player.onGround = true;
    gNm.player.lastSafeX = gNm.player.x;
    gNm.player.lastSafeY = gNm.player.y;
    gNm.player.lastSafeZ = gNm.player.z;
}

void nm_simulate_player() {
    const bool forward = nm_key_down('W');
    const bool backward = nm_key_down('S');
    const bool left = nm_key_down('A');
    const bool right = nm_key_down('D');
    const bool sneak = nm_key_down(VK_SHIFT);
    const bool sprint = nm_key_down(VK_CONTROL) && forward && !sneak;

    float inputForward = (forward ? 1.0f : 0.0f) - (backward ? 1.0f : 0.0f);
    float inputStrafe = (right ? 1.0f : 0.0f) - (left ? 1.0f : 0.0f);

    const float inputLen = std::sqrt(
        inputForward * inputForward + inputStrafe * inputStrafe
    );
    if (inputLen > 1.0f) {
        inputForward /= inputLen;
        inputStrafe /= inputLen;
    }

    const float speed = sneak
        ? SNEAK_SPEED
        : (sprint ? SPRINT_SPEED : WALK_SPEED);

    const float yaw = nm_radians(gNm.player.yaw);
    const float sinYaw = std::sin(yaw);
    const float cosYaw = std::cos(yaw);

    const float wishX =
        (-sinYaw * inputForward + cosYaw * inputStrafe) * speed;
    const float wishZ =
        ( cosYaw * inputForward + sinYaw * inputStrafe) * speed;

    const float accel = gNm.player.onGround ? GROUND_ACCEL : AIR_ACCEL;

    const float deltaX = wishX - gNm.player.vx;
    const float deltaZ = wishZ - gNm.player.vz;
    gNm.player.vx += deltaX > accel ? accel : (deltaX < -accel ? -accel : deltaX);
    gNm.player.vz += deltaZ > accel ? accel : (deltaZ < -accel ? -accel : deltaZ);

    if (inputLen == 0.0f && gNm.player.onGround) {
        gNm.player.vx *= 0.60f;
        gNm.player.vz *= 0.60f;
        if (std::fabs(gNm.player.vx) < 0.02f) gNm.player.vx = 0.0f;
        if (std::fabs(gNm.player.vz) < 0.02f) gNm.player.vz = 0.0f;
    }

    if (gNm.player.onGround && nm_key_pressed(VK_SPACE)) {
        gNm.player.vy = JUMP_VELOCITY;
        gNm.player.onGround = false;
    } else {
        const float falling = gNm.player.vy - GRAVITY;
        gNm.player.vy = falling > -MAX_FALL ? falling : -MAX_FALL;
    }

    float nextX = gNm.player.x;
    float nextY = gNm.player.y + gNm.player.vy;
    float nextZ = gNm.player.z;

    move_axis_with_voxels(nextX, gNm.player.x + gNm.player.vx, true);
    gNm.player.x = nextX;
    move_axis_with_voxels(nextZ, gNm.player.z + gNm.player.vz, false);

    nextX = gNm.player.x;
    nextZ = nextZ;

    resolve_sm64_walls(nextX, nextY, nextZ);

    Surface *floor = nullptr;
    const float floorY = find_floor(
        nextX, nextY + NM_PLAYER_HEIGHT, nextZ, &floor
    );

    Surface *ceil = nullptr;
    const float ceilY = find_ceil(
        nextX, nextY + 80.0f, nextZ, &ceil
    );

    bool onGround = false;

    if (gNm.player.vy <= 0.0f
        && floor != nullptr
        && floorY > FLOOR_LOWER_LIMIT
        && nextY <= floorY + 18.0f
        && gNm.player.y >= floorY - 90.0f) {
        nextY = floorY;
        gNm.player.vy = 0.0f;
        onGround = true;
    }

    if (gNm.player.vy > 0.0f
        && ceil != nullptr
        && ceilY < CELL_HEIGHT_LIMIT
        && nextY + NM_PLAYER_HEIGHT >= ceilY) {
        nextY = ceilY - NM_PLAYER_HEIGHT;
        gNm.player.vy = 0.0f;
    }

    nm_world_resolve_vertical(
        nextX, nextZ, gNm.player.y, nextY, gNm.player.vy, onGround
    );

    const bool nativeFloorValid =
        floor != nullptr
        && floorY > FLOOR_LOWER_LIMIT
        && nextY - floorY < 900.0f;

    if (nativeFloorValid || onGround) {
        gNm.player.lastSafeX = nextX;
        gNm.player.lastSafeY = nextY;
        gNm.player.lastSafeZ = nextZ;
    }

    if (nextY < FLOOR_LOWER_LIMIT + 300.0f
        || std::fabs(nextX) >= LEVEL_BOUNDARY_MAX - 80.0f
        || std::fabs(nextZ) >= LEVEL_BOUNDARY_MAX - 80.0f) {
        nextX = gNm.player.lastSafeX;
        nextY = gNm.player.lastSafeY;
        nextZ = gNm.player.lastSafeZ;
        gNm.player.vx = 0.0f;
        gNm.player.vy = 0.0f;
        gNm.player.vz = 0.0f;
        onGround = true;
    }

    gNm.player.x = nextX;
    gNm.player.y = nextY;
    gNm.player.z = nextZ;
    gNm.player.onGround = onGround;
}
