#include "native_minecraft_internal.h"

#include <cmath>
#include <fstream>
#include <sstream>

extern "C" {
#include "engine/surface_collision.h"
}

namespace {

constexpr int MAX_BLOCKS_PER_AREA = 4096;
constexpr const char *WORLD_FILE = "native_minecraft_world.dat";

bool player_intersects_block(float px, float py, float pz, const NmBlock &b) {
    const float minX = px - NM_PLAYER_RADIUS;
    const float maxX = px + NM_PLAYER_RADIUS;
    const float minY = py;
    const float maxY = py + NM_PLAYER_HEIGHT;
    const float minZ = pz - NM_PLAYER_RADIUS;
    const float maxZ = pz + NM_PLAYER_RADIUS;

    const float bx0 = b.x * NM_BLOCK;
    const float by0 = b.y * NM_BLOCK;
    const float bz0 = b.z * NM_BLOCK;
    const float bx1 = bx0 + NM_BLOCK;
    const float by1 = by0 + NM_BLOCK;
    const float bz1 = bz0 + NM_BLOCK;

    return maxX > bx0 && minX < bx1
        && maxY > by0 && minY < by1
        && maxZ > bz0 && minZ < bz1;
}

int block_index_at(const std::vector<NmBlock> &blocks, int bx, int by, int bz) {
    for (int i = 0; i < (int)blocks.size(); ++i) {
        const NmBlock &b = blocks[(size_t)i];
        if (b.x == bx && b.y == by && b.z == bz) return i;
    }
    return -1;
}

bool place_block(std::vector<NmBlock> &blocks, int bx, int by, int bz, int type) {
    if ((int)blocks.size() >= MAX_BLOCKS_PER_AREA) return false;
    if (block_index_at(blocks, bx, by, bz) >= 0) return false;

    NmBlock candidate{bx, by, bz, type};
    if (player_intersects_block(
            gNm.player.x, gNm.player.y, gNm.player.z, candidate)) {
        return false;
    }

    blocks.push_back(candidate);
    nm_world_save();
    return true;
}

} // namespace

int nm_world_key(int level, int area) {
    return ((level & 0xFFFF) << 8) | (area & 0xFF);
}

std::vector<NmBlock> &nm_current_blocks() {
    return gNm.worlds[nm_world_key(gNm.player.level, gNm.player.area)];
}

const std::vector<NmBlock> &nm_current_blocks_const() {
    static const std::vector<NmBlock> empty;
    const int key = nm_world_key(gNm.player.level, gNm.player.area);
    auto it = gNm.worlds.find(key);
    return it == gNm.worlds.end() ? empty : it->second;
}

void nm_world_load_once() {
    if (gNm.worldLoaded) return;
    gNm.worldLoaded = true;

    std::ifstream in(WORLD_FILE);
    if (!in) return;

    int level = 0;
    int area = 0;
    NmBlock b{};
    while (in >> level >> area >> b.x >> b.y >> b.z >> b.type) {
        auto &blocks = gNm.worlds[nm_world_key(level, area)];
        if ((int)blocks.size() < MAX_BLOCKS_PER_AREA
            && block_index_at(blocks, b.x, b.y, b.z) < 0) {
            blocks.push_back(b);
        }
    }
}

void nm_world_save() {
    std::ofstream out(WORLD_FILE, std::ios::trunc);
    if (!out) return;

    for (const auto &entry : gNm.worlds) {
        const int key = entry.first;
        const int level = (key >> 8) & 0xFFFF;
        const int area = key & 0xFF;
        for (const NmBlock &b : entry.second) {
            out << level << ' ' << area << ' '
                << b.x << ' ' << b.y << ' ' << b.z << ' ' << b.type << '\n';
        }
    }
}

bool nm_world_player_intersects(float x, float y, float z) {
    for (const NmBlock &b : nm_current_blocks_const()) {
        if (player_intersects_block(x, y, z, b)) return true;
    }
    return false;
}

void nm_world_resolve_vertical(
    float x, float z, float oldY, float &newY, float &vy, bool &onGround
) {
    for (const NmBlock &b : nm_current_blocks_const()) {
        const float bx0 = b.x * NM_BLOCK;
        const float bx1 = bx0 + NM_BLOCK;
        const float bz0 = b.z * NM_BLOCK;
        const float bz1 = bz0 + NM_BLOCK;

        if (x + NM_PLAYER_RADIUS <= bx0 || x - NM_PLAYER_RADIUS >= bx1
            || z + NM_PLAYER_RADIUS <= bz0
            || z - NM_PLAYER_RADIUS >= bz1) {
            continue;
        }

        const float bottom = b.y * NM_BLOCK;
        const float top = bottom + NM_BLOCK;

        if (vy <= 0.0f && oldY >= top - 25.0f && newY <= top) {
            newY = top;
            vy = 0.0f;
            onGround = true;
        } else if (vy > 0.0f
            && oldY + NM_PLAYER_HEIGHT <= bottom + 25.0f
            && newY + NM_PLAYER_HEIGHT >= bottom) {
            newY = bottom - NM_PLAYER_HEIGHT;
            vy = 0.0f;
        }
    }
}

void nm_world_interact() {
    const bool breakPressed = nm_key_pressed(VK_LBUTTON);
    const bool placePressed = nm_key_pressed(VK_RBUTTON);
    if (!breakPressed && !placePressed) return;

    auto &blocks = nm_current_blocks();

    const float yaw = gNm.player.yaw * 0.01745329251994329577f;
    const float pitch = gNm.player.pitch * 0.01745329251994329577f;
    const float cp = std::cos(pitch);
    const float dx = -std::sin(yaw) * cp;
    const float dy = -std::sin(pitch);
    const float dz = -std::cos(yaw) * cp;

    const float ox = gNm.player.x;
    const float oy = gNm.player.y + NM_EYE_HEIGHT;
    const float oz = gNm.player.z;

    int prevX = (int)std::floor(ox / NM_BLOCK);
    int prevY = (int)std::floor(oy / NM_BLOCK);
    int prevZ = (int)std::floor(oz / NM_BLOCK);

    for (float t = 18.0f; t <= 600.0f; t += 10.0f) {
        const float px = ox + dx * t;
        const float py = oy + dy * t;
        const float pz = oz + dz * t;

        const int bx = (int)std::floor(px / NM_BLOCK);
        const int by = (int)std::floor(py / NM_BLOCK);
        const int bz = (int)std::floor(pz / NM_BLOCK);

        const int hit = block_index_at(blocks, bx, by, bz);
        if (hit >= 0) {
            if (breakPressed) {
                blocks.erase(blocks.begin() + hit);
                nm_world_save();
            } else {
                place_block(
                    blocks, prevX, prevY, prevZ,
                    gNm.player.selectedSlot + 1
                );
            }
            return;
        }

        // SM64 geometry acts as a valid placement surface for the first native
        // block. Once blocks exist, normal adjacent-block placement takes over.
        struct Surface *floor = nullptr;
        const float floorY = find_floor(px, py + 35.0f, pz, &floor);
        if (placePressed
            && floor != nullptr
            && floorY > FLOOR_LOWER_LIMIT
            && py <= floorY + 24.0f
            && py >= floorY - 40.0f) {
            const int fy = (int)std::floor((floorY + 2.0f) / NM_BLOCK);
            place_block(blocks, bx, fy, bz, gNm.player.selectedSlot + 1);
            return;
        }

        prevX = bx;
        prevY = by;
        prevZ = bz;
    }
}

extern "C" int native_minecraft_block_count(void) {
    return (int)nm_current_blocks_const().size();
}

extern "C" int native_minecraft_get_block(
    int index, int *x, int *y, int *z, int *type
) {
    const auto &blocks = nm_current_blocks_const();
    if (index < 0 || index >= (int)blocks.size()) return 0;

    const NmBlock &b = blocks[(size_t)index];
    if (x) *x = b.x;
    if (y) *y = b.y;
    if (z) *z = b.z;
    if (type) *type = b.type;
    return 1;
}
