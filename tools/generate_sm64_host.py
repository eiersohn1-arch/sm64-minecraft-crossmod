#!/usr/bin/env python3
"""Patch a clean sm64-port checkout into the first real Universal Modder host.

Nothing from the legacy crossmod is reused.  The WebSocket implementation is
copied verbatim from Universal Modder's worked Minecraft passthrough example;
this script only adds a thin SM64 pose adapter and build/lifecycle hooks.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
UM = ROOT / "vendor" / "universal-modder"
SM64 = ROOT / "vendor" / "sm64-port"
REF = UM / "examples" / "minecraft-gta5-passthrough" / "gta" / "src"
PC = SM64 / "src" / "pc"

def patch_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch marker missing in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

if not (SM64 / "src" / "game" / "game_init.c").is_file():
    raise SystemExit("Run setup-windows.bat first.")

# Universal Modder transport, verbatim.
for name in ("ws.cpp", "ws.h"):
    shutil.copy2(REF / name, PC / name)

(PC / "sm64_passthrough.h").write_text(r'''#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void um_passthrough_start(void);
void um_passthrough_stop(void);
void um_passthrough_frame(void);
#ifdef __cplusplus
}
#endif
''', encoding="utf-8")

(PC / "sm64_passthrough.cpp").write_text(r'''#include "sm64_passthrough.h"
#include "ws.h"
#include <cstdio>

extern "C" {
#include "game/camera.h"
#include "game/mario.h"
}

static WsClient s_ws;
static unsigned long long s_frame = 0;

void um_passthrough_start(void) {
    s_ws.start("127.0.0.1", 25599);
}

void um_passthrough_stop(void) {
    s_ws.stop();
}

void um_passthrough_frame(void) {
    if (!s_ws.connected() || gMarioState == nullptr) {
        return;
    }

    // One SM64 world unit is mapped to one centimetre in the guest for this
    // first oracle.  The transform is deliberately isolated here so collision
    // and compositor milestones can share the exact same mapping later.
    constexpr float SCALE = 100.0f;
    constexpr float MC_Y_ORIGIN = 64.0f;

    const float cameraX = gLakituState.pos[0] / SCALE;
    const float cameraY = gLakituState.pos[1] / SCALE + MC_Y_ORIGIN;
    const float cameraZ = -gLakituState.pos[2] / SCALE;

    const float playerX = gMarioState->pos[0] / SCALE;
    const float playerY = gMarioState->pos[1] / SCALE + MC_Y_ORIGIN;
    const float playerZ = -gMarioState->pos[2] / SCALE;

    const float bodyYaw =
        180.0f
        - (float)gMarioState->faceAngle[1] * (360.0f / 65536.0f);

    const float dx = (gLakituState.focus[0] - gLakituState.pos[0]) / SCALE;
    const float dy = (gLakituState.focus[1] - gLakituState.pos[1]) / SCALE;
    const float dz = -(gLakituState.focus[2] - gLakituState.pos[2]) / SCALE;
    constexpr float RAD_TO_DEG = 57.29577951308232f;
    const float cameraYaw = std::atan2(-dx, dz) * RAD_TO_DEG;
    const float cameraPitch =
        -std::atan2(dy, std::sqrt(dx * dx + dz * dz)) * RAD_TO_DEG;

    // Milestone 1 is intentionally third person.  It proves that the real
    // SM64 camera/player drive the real Universal Modder Minecraft guest
    // before any custom compositor or collision code is introduced.
    char message[512];
    std::snprintf(
        message,
        sizeof(message),
        "{\"t\":\"cam\",\"f\":%llu,"
        "\"p\":[%.4f,%.4f,%.4f],"
        "\"r\":[%.3f,0,0],"
        "\"fov\":60,\"fp\":false,"
        "\"pl\":[%.4f,%.4f,%.4f],\"h\":%.3f}",
        ++s_frame,
        cameraX, cameraY, cameraZ,
        bodyYaw,
        playerX, playerY, playerZ,
        bodyYaw
    );
    s_ws.send(message);
}
''', encoding="utf-8")

pc_main = PC / "pc_main.c"
patch_once(
    pc_main,
    '#include "configfile.h"\n',
    '#include "configfile.h"\n#include "sm64_passthrough.h"\n',
)
patch_once(
    pc_main,
    "    game_loop_one_iteration();\n",
    "    game_loop_one_iteration();\n"
    "    um_passthrough_frame();\n",
)
patch_once(
    pc_main,
    '    gfx_init(wm_api, rendering_api, "Super Mario 64 PC-Port", configFullscreen);\n',
    '    gfx_init(wm_api, rendering_api, "Super Mario 64 PC-Port", configFullscreen);\n'
    '    um_passthrough_start();\n'
    '    atexit(um_passthrough_stop);\n',
)

makefile = SM64 / "Makefile"
patch_once(
    makefile,
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -no-pie -mwindows",
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -no-pie -mwindows",
)

print("Clean SM64 Universal Modder host installed into:", SM64)
print("Transport: Universal Modder ws.cpp/ws.h on 127.0.0.1:25599")
print("Lifecycle: SM64 starts/stops the link and publishes one camera pose per frame")
