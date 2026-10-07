#include "native_minecraft_internal.h"

#include <algorithm>
#include <cstring>

#define WIN32_LEAN_AND_MEAN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

NmRuntimeState gNm;

extern "C" void native_minecraft_key_event(int vk, int down) {
    if (vk < 0 || vk >= (int)gNm.input.down.size()) return;

    const bool wasDown = gNm.input.down[(size_t)vk] != 0;
    const bool isDown = down != 0;
    gNm.input.down[(size_t)vk] = isDown ? 1 : 0;
    if (isDown && !wasDown) {
        gNm.input.pressed[(size_t)vk] = 1;
    }
}

extern "C" void native_minecraft_mouse_button(int button, int down) {
    int vk = 0;
    if (button == 0) vk = VK_LBUTTON;
    if (button == 1) vk = VK_RBUTTON;
    if (button == 2) vk = VK_MBUTTON;
    if (vk != 0) native_minecraft_key_event(vk, down);
}

extern "C" void native_minecraft_raw_mouse(int dx, int dy) {
    if (!gNm.input.focused) return;
    gNm.input.rawMouseX += dx;
    gNm.input.rawMouseY += dy;
}

extern "C" void native_minecraft_focus_changed(int focused) {
    gNm.input.focused = focused != 0;
    if (!gNm.input.focused) {
        gNm.input.down.fill(0);
        gNm.input.pressed.fill(0);
        gNm.input.rawMouseX = 0;
        gNm.input.rawMouseY = 0;
    }
}

bool nm_key_down(int vk) {
    return gNm.input.focused
        && vk >= 0
        && vk < (int)gNm.input.down.size()
        && gNm.input.down[(size_t)vk] != 0;
}

bool nm_key_pressed(int vk) {
    return gNm.input.focused
        && vk >= 0
        && vk < (int)gNm.input.pressed.size()
        && gNm.input.pressed[(size_t)vk] != 0;
}

void nm_input_begin_frame() {
    if (!gNm.input.focused) return;

    // Raw WM_INPUT deltas are accumulated independently of SM64's 30 Hz game loop.
    // This prevents the cursor-warp / missed-delta behaviour from the prototype.
    constexpr float sensitivity = 0.115f;
    gNm.player.yaw += (float)gNm.input.rawMouseX * sensitivity;
    gNm.player.pitch += (float)gNm.input.rawMouseY * sensitivity;
    gNm.input.rawMouseX = 0;
    gNm.input.rawMouseY = 0;

    gNm.player.pitch = std::clamp(gNm.player.pitch, -89.0f, 89.0f);
    while (gNm.player.yaw >= 180.0f) gNm.player.yaw -= 360.0f;
    while (gNm.player.yaw < -180.0f) gNm.player.yaw += 360.0f;

    if (nm_key_pressed(VK_F5)) {
        gNm.player.firstPerson = !gNm.player.firstPerson;
    }

    for (int i = 0; i < 9; ++i) {
        if (nm_key_pressed('1' + i)) {
            gNm.player.selectedSlot = i;
        }
    }
}

void nm_input_end_frame() {
    gNm.input.pressed.fill(0);
}
