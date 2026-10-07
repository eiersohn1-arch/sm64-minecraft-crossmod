#include "sm64_passthrough.h"
#include "ws.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <string>
#include <unordered_set>
#include <unordered_map>
#include <cstdlib>

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
#include "engine/surface_load.h"
#include "game/area.h"
#include "game/camera.h"
#include "game/level_update.h"
#include "game/mario.h"

extern struct CameraFOVStatus sFOVState;
}

namespace {

int at_least(int value, int minimum) {
    return value < minimum ? minimum : value;
}

constexpr float SCALE = 100.0f;
constexpr float MC_Y0 = 64.0f;
constexpr float RAD_TO_DEG = 57.29577951308232f;
constexpr float DEG_TO_RAD = 0.01745329251994329577f;

WsClient g_ws;
unsigned long long g_hostFrame = 0;
int g_generation = -1;
int g_save = -1;
int g_level = -1;
int g_area = -1;
double g_worldOffsetX = 0.0;
double g_worldOffsetZ = 0.0;
std::unordered_set<unsigned long long> g_collisionSampled;

struct McBlockCoord {
    int x;
    int y;
    int z;
};
std::unordered_map<unsigned long long, McBlockCoord> g_minecraftBlocks;

std::array<std::atomic<unsigned char>, 256> g_keys{};
std::array<std::atomic<unsigned char>, 256> g_pressed{};
std::atomic<int> g_rawMouseX{0};
std::atomic<int> g_rawMouseY{0};
std::atomic<int> g_wheel{0};
std::atomic<int> g_pointerX{0};
std::atomic<int> g_pointerY{0};
std::atomic<int> g_viewWidth{640};
std::atomic<int> g_viewHeight{480};
std::atomic<bool> g_pointerDirty{true};
std::atomic<bool> g_viewDirty{true};
std::atomic<bool> g_focused{true};

bool g_attack = false;
bool g_use = false;
bool g_inventory = false;
bool g_drop = false;
bool g_swap = false;
bool g_escape = false;
bool g_uiLeft = false;
bool g_uiRight = false;
bool g_uiMiddle = false;
bool g_firstPerson = false;
bool g_inventoryScreen = false;
bool g_spawnSyncPending = false;
bool g_semanticJumpPrev = false;
bool g_semanticAttackPrev = false;
bool g_semanticUsePrev = false;
bool g_semanticSneakPrev = false;
int g_driveDelayFrames = 0;

struct McPose {
    bool valid = false;
    double x = 0.0;
    double y = MC_Y0;
    double z = 0.0;
    double vx = 0.0;
    double vy = 0.0;
    double vz = 0.0;
    float yaw = 0.0f;
    float pitch = 0.0f;
};

McPose g_mc;

unsigned long long minecraft_block_key(int x, int y, int z) {
    const unsigned long long ux = static_cast<unsigned int>(x);
    const unsigned long long uy = static_cast<unsigned int>(y);
    const unsigned long long uz = static_cast<unsigned int>(z);
    return (ux * 0x9E3779B185EBCA87ULL)
        ^ (uy * 0xC2B2AE3D27D4EB4FULL)
        ^ (uz * 0x165667B19E3779F9ULL);
}

void apply_block_array(const std::string &message, const char *field, bool add) {
    const std::string marker = std::string("\"") + field + "\":[";
    const size_t at = message.find(marker);
    if (at == std::string::npos) return;

    const char *p = message.c_str() + at + marker.size();
    const char *end = message.c_str() + message.size();

    while (p < end && *p != ']') {
        char *next = nullptr;
        const long x = std::strtol(p, &next, 10);
        if (next == p) break;
        p = next;
        if (p >= end || *p++ != ',') break;

        const long y = std::strtol(p, &next, 10);
        if (next == p) break;
        p = next;
        if (p >= end || *p++ != ',') break;

        const long z = std::strtol(p, &next, 10);
        if (next == p) break;
        p = next;

        const int ix = static_cast<int>(x);
        const int iy = static_cast<int>(y);
        const int iz = static_cast<int>(z);
        const auto key = minecraft_block_key(ix, iy, iz);

        if (add) {
            if (g_minecraftBlocks.size() < 4096 || g_minecraftBlocks.count(key)) {
                g_minecraftBlocks[key] = { ix, iy, iz };
            }
        } else {
            g_minecraftBlocks.erase(key);
        }

        if (p < end && *p == ',') ++p;
    }
}

void update_world_zone() {
    const int save = gCurrSaveFileNum > 0 ? gCurrSaveFileNum - 1 : 0;
    const int level = gCurrLevelNum > 0 ? gCurrLevelNum : 0;
    const int area = gCurrAreaIndex > 0 ? gCurrAreaIndex : 0;
    const int index = save * 256 + level * 8 + area;

    constexpr int GRID = 32;
    constexpr double STRIDE = 512.0;
    g_worldOffsetX = static_cast<double>(index % GRID) * STRIDE;
    g_worldOffsetZ = static_cast<double>(index / GRID) * STRIDE;
}

bool host_has_focus() {
    return g_focused.load(std::memory_order_relaxed);
}

bool key_down(int vk) {
    return host_has_focus()
        && vk >= 0
        && vk < static_cast<int>(g_keys.size())
        && g_keys[static_cast<size_t>(vk)].load(std::memory_order_relaxed) != 0;
}

bool take_pressed(int vk) {
    if (vk < 0 || vk >= static_cast<int>(g_pressed.size())) return false;
    return g_pressed[static_cast<size_t>(vk)].exchange(
        0, std::memory_order_relaxed) != 0;
}

bool native_sm64_action_owns_player() {
    if (gMarioState == nullptr || gCamera == nullptr) return true;
    if (gCamera->cutscene != 0) return true;

    const u32 group = gMarioState->action & ACT_GROUP_MASK;
    return group == ACT_GROUP_CUTSCENE
        || group == ACT_GROUP_AUTOMATIC
        || group == ACT_GROUP_OBJECT
        || group == ACT_GROUP_SUBMERGED;
}

void poll_guest_messages() {
    std::string message;
    while (g_ws.poll(message)) {
        if (message.find("\"t\":\"blocks\"") != std::string::npos) {
            apply_block_array(message, "set", true);
            apply_block_array(message, "clear", false);
            continue;
        }

        if (message.find("\"t\":\"screen\"") != std::string::npos) {
            const bool open =
                message.find("\"open\":true") != std::string::npos;
            g_inventoryScreen = open;
            if (!open) {
                g_uiLeft = false;
                g_uiRight = false;
                g_uiMiddle = false;
            }
            continue;
        }

        McPose pose;
        const int matched = std::sscanf(
            message.c_str(),
            "{\"t\":\"mcpos\",\"pos\":[%lf,%lf,%lf],"
            "\"vel\":[%lf,%lf,%lf],\"r\":[%f,%f]",
            &pose.x, &pose.y, &pose.z,
            &pose.vx, &pose.vy, &pose.vz,
            &pose.yaw, &pose.pitch
        );
        if (matched == 8) {
            pose.valid = std::isfinite(pose.x)
                && std::isfinite(pose.y)
                && std::isfinite(pose.z)
                && std::isfinite(pose.vx)
                && std::isfinite(pose.vy)
                && std::isfinite(pose.vz)
                && std::isfinite(pose.yaw)
                && std::isfinite(pose.pitch);
            if (pose.valid) g_mc = pose;
        }
    }
}

void send_ui_button(int button, int vk, bool &previous) {
    const bool now = key_down(vk);
    if (now == previous) return;

    previous = now;

    const int w = at_least(g_viewWidth.load(std::memory_order_relaxed), 1);
    const int h = at_least(g_viewHeight.load(std::memory_order_relaxed), 1);
    const double nx = std::clamp(
        static_cast<double>(g_pointerX.load(std::memory_order_relaxed)) / w,
        0.0, 1.0
    );
    const double ny = std::clamp(
        static_cast<double>(g_pointerY.load(std::memory_order_relaxed)) / h,
        0.0, 1.0
    );

    char msg[160];
    std::snprintf(
        msg, sizeof(msg),
        "{\"t\":\"uibutton\",\"b\":%d,\"down\":%s,"
        "\"x\":%.6f,\"y\":%.6f}",
        button, now ? "true" : "false", nx, ny
    );
    g_ws.send(msg);
}

void send_key(const char *name, int vk, bool &previous) {
    const bool now = key_down(vk);
    if (now == previous) return;

    previous = now;
    char msg[96];
    std::snprintf(
        msg, sizeof(msg),
        "{\"t\":\"key\",\"k\":\"%s\",\"down\":%s}",
        name, now ? "true" : "false"
    );
    g_ws.send(msg);
}

void publish_input() {
    if (!g_ws.connected()) return;

    if (!host_has_focus()) {
        g_rawMouseX.exchange(0);
        g_rawMouseY.exchange(0);
        g_wheel.exchange(0);
    }

    if (take_pressed(VK_F5)) {
        g_firstPerson = !g_firstPerson;
    }

    if (take_pressed('E')) {
        g_inventoryScreen = !g_inventoryScreen;
    }
    if (take_pressed(VK_ESCAPE)) {
        g_inventoryScreen = false;
    }

    send_key("attack", VK_LBUTTON, g_attack);
    send_key("use", VK_RBUTTON, g_use);
    send_key("inventory", 'E', g_inventory);
    send_key("drop", 'Q', g_drop);
    send_key("swap", 'F', g_swap);
    send_key("escape", VK_ESCAPE, g_escape);

    // Screen-space clicks are separate from gameplay attack/use so real
    // Minecraft inventory/container screens remain fully interactive.
    send_ui_button(1, VK_LBUTTON, g_uiLeft);
    send_ui_button(3, VK_RBUTTON, g_uiRight);
    send_ui_button(2, VK_MBUTTON, g_uiMiddle);

    if (g_viewDirty.exchange(false, std::memory_order_relaxed)) {
        const int w = at_least(g_viewWidth.load(std::memory_order_relaxed), 320);
        const int h = at_least(g_viewHeight.load(std::memory_order_relaxed), 240);
        char view[96];
        std::snprintf(
            view, sizeof(view),
            "{\"t\":\"view\",\"w\":%d,\"h\":%d}", w, h
        );
        g_ws.send(view);
    }

    if (g_pointerDirty.exchange(false, std::memory_order_relaxed)) {
        const int w = at_least(g_viewWidth.load(std::memory_order_relaxed), 1);
        const int h = at_least(g_viewHeight.load(std::memory_order_relaxed), 1);
        const double nx = std::clamp(
            static_cast<double>(g_pointerX.load(std::memory_order_relaxed)) / w,
            0.0, 1.0
        );
        const double ny = std::clamp(
            static_cast<double>(g_pointerY.load(std::memory_order_relaxed)) / h,
            0.0, 1.0
        );
        char pointer[112];
        std::snprintf(
            pointer, sizeof(pointer),
            "{\"t\":\"pointer\",\"x\":%.6f,\"y\":%.6f}",
            nx, ny
        );
        g_ws.send(pointer);
    }

    for (int i = 0; i < 9; ++i) {
        if (take_pressed('1' + i)) {
            char msg[48];
            std::snprintf(
                msg, sizeof(msg),
                "{\"t\":\"slot\",\"n\":%d}", i
            );
            g_ws.send(msg);
        }
    }

    const int wheel = g_wheel.exchange(0, std::memory_order_relaxed);
    if (wheel != 0) {
        const int direction = wheel > 0 ? 1 : -1;
        char msg[64];
        std::snprintf(
            msg, sizeof(msg),
            "{\"t\":\"scroll\",\"d\":%d}", direction
        );
        g_ws.send(msg);
    }

    const bool forward = key_down('W') && !g_inventoryScreen;
    const bool back = key_down('S') && !g_inventoryScreen;
    const bool left = key_down('A') && !g_inventoryScreen;
    const bool right = key_down('D') && !g_inventoryScreen;
    const bool jump = key_down(VK_SPACE) && !g_inventoryScreen;
    const bool sneak = key_down(VK_SHIFT) && !g_inventoryScreen;
    const bool sprint = key_down(VK_CONTROL) && !g_inventoryScreen;

    char movement[224];
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
    g_ws.send(movement);

    const int dx = g_rawMouseX.exchange(0, std::memory_order_relaxed);
    const int dy = g_rawMouseY.exchange(0, std::memory_order_relaxed);
    if (!g_inventoryScreen && (dx != 0 || dy != 0)) {
        char look[128];
        std::snprintf(
            look, sizeof(look),
            "{\"t\":\"look\",\"dx\":%d,\"dy\":%d}", dx, dy
        );
        g_ws.send(look);
    }
}

unsigned long long column_key(int x, int z) {
    return (static_cast<unsigned long long>(
        static_cast<unsigned int>(x)) << 32)
        | static_cast<unsigned int>(z);
}

void append_column(
    std::string &cols,
    int x, int z, int bottom, int top
) {
    if (top < bottom) return;

    char entry[80];
    std::snprintf(
        entry, sizeof(entry),
        "%s%d,%d,%d,%d",
        cols.empty() ? "" : ",",
        x, z, bottom, top
    );
    cols += entry;
}

void reset_collision_if_needed() {
    const int generation = g_ws.generation();
    if (generation == g_generation
        && gCurrSaveFileNum == g_save
        && gCurrLevelNum == g_level
        && gCurrAreaIndex == g_area) {
        return;
    }

    g_generation = generation;
    g_save = gCurrSaveFileNum;
    g_level = gCurrLevelNum;
    g_area = gCurrAreaIndex;
    update_world_zone();

    g_collisionSampled.clear();
    g_minecraftBlocks.clear();
    g_mc.valid = false;
    g_spawnSyncPending = true;
    g_driveDelayFrames = 10;

    char context[160];
    std::snprintf(
        context, sizeof(context),
        "{\"t\":\"surfacectx\",\"k\":\"save%d-level%d-area%d\"}",
        g_save, g_level, g_area
    );
    g_ws.send(context);
}

void publish_collision() {
    if (!gMarioState || !gCurrentArea) return;

    constexpr int RADIUS = 16;
    constexpr int BUDGET = 160;

    const int cx = static_cast<int>(
        std::floor(gMarioState->pos[0] / SCALE));
    const int cz = static_cast<int>(
        std::floor(-gMarioState->pos[2] / SCALE));

    const float probeY = gMarioState->pos[1];
    std::string cols;
    int probes = 0;

    for (int dz = -RADIUS; dz <= RADIUS && probes < BUDGET; ++dz) {
        for (int dx = -RADIUS; dx <= RADIUS && probes < BUDGET; ++dx) {
            if (dx * dx + dz * dz > RADIUS * RADIUS) continue;

            const int x = cx + dx + static_cast<int>(g_worldOffsetX);
            const int z = cz + dz + static_cast<int>(g_worldOffsetZ);
            const auto key = column_key(x, z);
            if (g_collisionSampled.count(key)) continue;

            ++probes;
            g_collisionSampled.insert(key);

            const float sx =
                (static_cast<float>(x) + 0.5f - static_cast<float>(g_worldOffsetX)) * SCALE;
            const float sz =
                -(static_cast<float>(z) + 0.5f - static_cast<float>(g_worldOffsetZ)) * SCALE;

            struct Surface *floor = nullptr;
            const float floorY = find_floor(
                sx, probeY + 900.0f, sz, &floor
            );

            int floorTop = 0;
            bool haveFloor = floor != nullptr
                && floorY > FLOOR_LOWER_LIMIT;

            if (haveFloor) {
                floorTop = static_cast<int>(
                    std::floor(floorY / SCALE + MC_Y0 + 0.5f)
                ) - 1;
                append_column(
                    cols, x, z,
                    floorTop - 3, floorTop
                );
            }

            struct Surface *ceil = nullptr;
            const float ceilY = find_ceil(
                sx, probeY + 40.0f, sz, &ceil
            );
            if (ceil != nullptr
                && ceilY < CELL_HEIGHT_LIMIT
                && ceilY > probeY + 30.0f
                && ceilY - probeY < 700.0f) {
                const int ceilBlock = static_cast<int>(
                    std::floor(ceilY / SCALE + MC_Y0)
                );
                append_column(
                    cols, x, z,
                    ceilBlock, ceilBlock + 1
                );
            }

            WallCollisionData wall{};
            wall.x = sx;
            wall.y = probeY;
            wall.z = sz;
            wall.offsetY = 90.0f;
            wall.radius = 44.0f;
            find_wall_collisions(&wall);

            if (wall.numWalls > 0 && haveFloor) {
                append_column(
                    cols, x, z,
                    floorTop + 1, floorTop + 4
                );
            }
        }
    }

    if (!cols.empty()) {
        g_ws.send(
            "{\"t\":\"ground\",\"c\":[" + cols + "]}"
        );
    }

    if (g_spawnSyncPending && !cols.empty()) {
        const double x = gMarioState->pos[0] / SCALE + g_worldOffsetX;
        const double y = gMarioState->pos[1] / SCALE + MC_Y0 + 0.12;
        const double z = -gMarioState->pos[2] / SCALE + g_worldOffsetZ;

        char command[192];
        std::snprintf(
            command, sizeof(command),
            "{\"t\":\"cmd\",\"c\":\"tp @a %.4f %.4f %.4f\"}",
            x, y, z
        );
        g_ws.send(command);
        g_ws.send("{\"t\":\"cmd\",\"c\":\"gamemode survival @a\"}");
        g_ws.send("{\"t\":\"blocksync\",\"r\":48}");
        g_spawnSyncPending = false;
    }
}

void load_minecraft_block_collision() {
    for (const auto &entry : g_minecraftBlocks) {
        const McBlockCoord &block = entry.second;

        const float minX =
            (static_cast<float>(block.x) - static_cast<float>(g_worldOffsetX)) * SCALE;
        const float maxX = minX + SCALE;
        const float minY =
            (static_cast<float>(block.y) - MC_Y0) * SCALE;
        const float maxY = minY + SCALE;
        const float minZ =
            -(static_cast<float>(block.z + 1) - static_cast<float>(g_worldOffsetZ)) * SCALE;
        const float maxZ = minZ + SCALE;

        if (minX <= -8190.0f || maxX >= 8190.0f
            || minZ <= -8190.0f || maxZ >= 8190.0f
            || minY <= -8190.0f || maxY >= 8190.0f) {
            continue;
        }

        crossmod_add_dynamic_box(
            static_cast<s16>(std::lround(minX)),
            static_cast<s16>(std::lround(minY)),
            static_cast<s16>(std::lround(minZ)),
            static_cast<s16>(std::lround(maxX)),
            static_cast<s16>(std::lround(maxY)),
            static_cast<s16>(std::lround(maxZ))
        );
    }
}

} // namespace

void um_passthrough_key_event(int vk, int down) {
    if (vk < 0 || vk >= static_cast<int>(g_keys.size())) return;

    const auto i = static_cast<size_t>(vk);
    const unsigned char value = down ? 1 : 0;
    const unsigned char old = g_keys[i].exchange(
        value, std::memory_order_relaxed
    );
    if (value && !old) {
        g_pressed[i].store(1, std::memory_order_relaxed);
    }
}

void um_passthrough_mouse_button(int button, int down) {
    const int vk = button == 0 ? VK_LBUTTON
        : button == 1 ? VK_RBUTTON
        : button == 2 ? VK_MBUTTON
        : 0;
    if (vk != 0) um_passthrough_key_event(vk, down);
}

void um_passthrough_raw_mouse(int dx, int dy) {
    if (!host_has_focus()) return;
    g_rawMouseX.fetch_add(dx, std::memory_order_relaxed);
    g_rawMouseY.fetch_add(dy, std::memory_order_relaxed);
}

void um_passthrough_scroll(int delta) {
    if (!host_has_focus()) return;
    g_wheel.fetch_add(delta, std::memory_order_relaxed);
}

void um_passthrough_pointer(int x, int y, int width, int height) {
    if (width <= 0 || height <= 0) return;
    g_pointerX.store(x, std::memory_order_relaxed);
    g_pointerY.store(y, std::memory_order_relaxed);
    g_viewWidth.store(width, std::memory_order_relaxed);
    g_viewHeight.store(height, std::memory_order_relaxed);
    g_pointerDirty.store(true, std::memory_order_relaxed);
}

void um_passthrough_view(int width, int height) {
    if (width < 320 || height < 240) return;
    const int oldW = g_viewWidth.exchange(width, std::memory_order_relaxed);
    const int oldH = g_viewHeight.exchange(height, std::memory_order_relaxed);
    if (oldW != width || oldH != height) {
        g_viewDirty.store(true, std::memory_order_relaxed);
        g_pointerDirty.store(true, std::memory_order_relaxed);
    }
}

void um_passthrough_focus_changed(int focused) {
    g_focused.store(focused != 0, std::memory_order_relaxed);
    if (focused) return;

    for (auto &key : g_keys) key.store(0, std::memory_order_relaxed);
    for (auto &pressed : g_pressed) {
        pressed.store(0, std::memory_order_relaxed);
    }
    g_rawMouseX.store(0, std::memory_order_relaxed);
    g_rawMouseY.store(0, std::memory_order_relaxed);
    g_wheel.store(0, std::memory_order_relaxed);
    g_pointerDirty.store(true, std::memory_order_relaxed);
}

int um_passthrough_pointer_locked(void) {
    return g_ws.connected()
        && host_has_focus()
        && !g_inventoryScreen;
}

void um_passthrough_start(void) {
    g_ws.start("127.0.0.1", 25599);
}

void um_passthrough_stop(void) {
    g_ws.stop();
}

int um_passthrough_connected(void) {
    return g_ws.connected() ? 1 : 0;
}

int um_passthrough_minecraft_authority(void) {
    return g_ws.connected()
        && g_mc.valid
        && !native_sm64_action_owns_player();
}

void um_passthrough_neutralize_controller(struct MarioState *m) {
    if (!m || !m->controller || !um_passthrough_minecraft_authority()) {
        return;
    }

    m->controller->rawStickX = 0;
    m->controller->rawStickY = 0;
    m->controller->stickX = 0.0f;
    m->controller->stickY = 0.0f;
    m->controller->stickMag = 0.0f;
    m->controller->buttonDown = 0;
    m->controller->buttonPressed = 0;

    if (g_inventoryScreen) {
        g_semanticJumpPrev = false;
        g_semanticAttackPrev = false;
        g_semanticUsePrev = false;
        g_semanticSneakPrev = false;
        return;
    }

    const bool jump = key_down(VK_SPACE);
    const bool attack = key_down(VK_LBUTTON);
    const bool use = key_down(VK_RBUTTON);
    const bool sneak = key_down(VK_SHIFT);

    if (jump) m->controller->buttonDown |= A_BUTTON;
    if (attack || use) m->controller->buttonDown |= B_BUTTON;
    if (sneak) m->controller->buttonDown |= Z_TRIG;

    if (jump && !g_semanticJumpPrev) {
        m->controller->buttonPressed |= A_BUTTON;
    }
    if ((attack && !g_semanticAttackPrev)
        || (use && !g_semanticUsePrev)) {
        m->controller->buttonPressed |= B_BUTTON;
    }
    if (sneak && !g_semanticSneakPrev) {
        m->controller->buttonPressed |= Z_TRIG;
    }

    g_semanticJumpPrev = jump;
    g_semanticAttackPrev = attack;
    g_semanticUsePrev = use;
    g_semanticSneakPrev = sneak;
}

void um_passthrough_apply_mario_proxy(struct MarioState *m) {
    if (!m || !m->marioObj || !um_passthrough_minecraft_authority()) {
        return;
    }

    constexpr float ANGLE = 65536.0f / 360.0f;

    const float nextX = static_cast<float>((g_mc.x - g_worldOffsetX) * SCALE);
    const float nextY = static_cast<float>((g_mc.y - MC_Y0) * SCALE);
    const float nextZ = static_cast<float>(-(g_mc.z - g_worldOffsetZ) * SCALE);

    if (!std::isfinite(nextX)
        || !std::isfinite(nextY)
        || !std::isfinite(nextZ)
        || std::fabs(nextX) >= LEVEL_BOUNDARY_MAX - 64.0f
        || std::fabs(nextZ) >= LEVEL_BOUNDARY_MAX - 64.0f
        || nextY < FLOOR_LOWER_LIMIT + 150.0f
        || nextY > CELL_HEIGHT_LIMIT - 150.0f) {
        g_mc.valid = false;
        g_spawnSyncPending = true;
        g_driveDelayFrames = 10;
        return;
    }

    struct Surface *nextFloor = nullptr;
    const float floorY = find_floor(
        nextX, nextY + 900.0f, nextZ, &nextFloor
    );

    // Minecraft owns locomotion. A missing native floor is allowed here because
    // the user may have mined the mirrored SM64 surface in Minecraft.
    m->pos[0] = nextX;
    m->pos[1] = nextY;
    m->pos[2] = nextZ;
    if (nextFloor != nullptr && floorY > FLOOR_LOWER_LIMIT) {
        m->floor = nextFloor;
        m->floorHeight = floorY;
    } else {
        m->floor = nullptr;
        m->floorHeight = FLOOR_LOWER_LIMIT;
    }

    m->vel[0] = static_cast<float>(g_mc.vx * SCALE);
    m->vel[1] = static_cast<float>(g_mc.vy * SCALE);
    m->vel[2] = static_cast<float>(-g_mc.vz * SCALE);
    m->forwardVel = static_cast<float>(
        std::sqrt(g_mc.vx * g_mc.vx + g_mc.vz * g_mc.vz) * SCALE
    );

    const float sm64Yaw = 180.0f - g_mc.yaw;
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
}

void um_passthrough_override_camera(void) {
    if (!um_passthrough_minecraft_authority() || gCamera == nullptr) {
        return;
    }

    const float yaw = g_mc.yaw * DEG_TO_RAD;
    const float pitch = g_mc.pitch * DEG_TO_RAD;
    const float cp = std::cos(pitch);

    const float fx = -std::sin(yaw) * cp;
    const float fy = -std::sin(pitch);
    const float fz = -std::cos(yaw) * cp;

    const float eyeX = static_cast<float>((g_mc.x - g_worldOffsetX) * SCALE);
    const float eyeY = static_cast<float>(
        (g_mc.y - MC_Y0 + 1.62) * SCALE
    );
    const float eyeZ = static_cast<float>(-(g_mc.z - g_worldOffsetZ) * SCALE);

    const float distance = g_firstPerson ? 0.0f : 400.0f;

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
    sFOVState.fov = 70.0f;
    sFOVState.fovOffset = 0.0f;
}

void um_passthrough_before_frame(void) {
    if (!g_ws.connected()) return;

    poll_guest_messages();

    if (gMarioState && gMarioState->marioObj) {
        gMarioState->marioObj->header.gfx.node.flags
            |= GRAPH_RENDER_INVISIBLE;
    }
}

void um_passthrough_frame(void) {
    if (!g_ws.connected() || !gMarioState) return;

    reset_collision_if_needed();

    if (!g_spawnSyncPending && g_driveDelayFrames > 0) {
        --g_driveDelayFrames;
    }

    const bool drive =
        !native_sm64_action_owns_player()
        && !g_spawnSyncPending
        && g_driveDelayFrames == 0;

    const float camX = gLakituState.curPos[0] / SCALE + static_cast<float>(g_worldOffsetX);
    const float camY = gLakituState.curPos[1] / SCALE + MC_Y0;
    const float camZ = -gLakituState.curPos[2] / SCALE + static_cast<float>(g_worldOffsetZ);

    const float playerX = gMarioState->pos[0] / SCALE + static_cast<float>(g_worldOffsetX);
    const float playerY = gMarioState->pos[1] / SCALE + MC_Y0;
    const float playerZ = -gMarioState->pos[2] / SCALE + static_cast<float>(g_worldOffsetZ);

    const float dx =
        (gLakituState.curFocus[0] - gLakituState.curPos[0]) / SCALE;
    const float dy =
        (gLakituState.curFocus[1] - gLakituState.curPos[1]) / SCALE;
    const float dz =
        -(gLakituState.curFocus[2] - gLakituState.curPos[2]) / SCALE;

    float yaw = std::atan2(-dx, dz) * RAD_TO_DEG;
    float pitch = -std::atan2(
        dy, std::sqrt(dx * dx + dz * dz)
    ) * RAD_TO_DEG;

    float bodyYaw = 180.0f
        - static_cast<float>(gMarioState->faceAngle[1])
          * (360.0f / 65536.0f);

    if (drive && g_mc.valid) {
        yaw = g_mc.yaw;
        pitch = g_mc.pitch;
        bodyYaw = g_mc.yaw;
    }

    char msg[720];
    std::snprintf(
        msg, sizeof(msg),
        "{\"t\":\"cam\",\"f\":%llu,"
        "\"p\":[%.4f,%.4f,%.4f],"
        "\"r\":[%.3f,%.3f,0],\"fov\":70,"
        "\"fp\":%s,"
        "\"pl\":[%.4f,%.4f,%.4f],"
        "\"h\":%.3f,"
        "\"drive\":%s,"
        "\"look\":[%.3f,%.3f]}",
        ++g_hostFrame,
        camX, camY, camZ,
        yaw, pitch,
        g_firstPerson ? "true" : "false",
        playerX, playerY, playerZ,
        bodyYaw,
        drive ? "true" : "false",
        yaw, pitch
    );
    g_ws.send(msg);

    publish_collision();
    publish_input();
}


void um_passthrough_load_block_surfaces(void) {
    if (!g_ws.connected()) return;
    load_minecraft_block_collision();
}
