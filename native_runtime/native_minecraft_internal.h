#pragma once

#include "native_minecraft.h"

#include <array>
#include <map>
#include <vector>

struct NmInputState {
    std::array<unsigned char, 256> down{};
    std::array<unsigned char, 256> pressed{};
    int rawMouseX = 0;
    int rawMouseY = 0;
    bool focused = true;
};

struct NmPlayerState {
    bool initialized = false;
    bool onGround = false;
    bool firstPerson = false;
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
    float lastSafeX = 0.0f;
    float lastSafeY = 0.0f;
    float lastSafeZ = 0.0f;
};

struct NmBlock {
    int x = 0;
    int y = 0;
    int z = 0;
    int type = 1;
};

struct NmRuntimeState {
    NmInputState input;
    NmPlayerState player;
    std::map<int, std::vector<NmBlock>> worlds;
    bool authority = false;
    bool worldLoaded = false;
};

extern NmRuntimeState gNm;

constexpr float NM_BLOCK = 100.0f;
constexpr float NM_PLAYER_RADIUS = 30.0f;
constexpr float NM_PLAYER_HEIGHT = 180.0f;
constexpr float NM_EYE_HEIGHT = 162.0f;

int nm_world_key(int level, int area);
std::vector<NmBlock> &nm_current_blocks();
const std::vector<NmBlock> &nm_current_blocks_const();

void nm_input_begin_frame();
void nm_input_end_frame();
bool nm_key_down(int vk);
bool nm_key_pressed(int vk);

void nm_sync_player_from_mario(struct MarioState *m);
void nm_simulate_player();
bool nm_should_have_authority(const struct MarioState *m);

void nm_world_load_once();
void nm_world_save();
void nm_world_interact();
bool nm_world_player_intersects(float x, float y, float z);
void nm_world_resolve_vertical(float x, float z, float oldY, float &newY, float &vy, bool &onGround);
