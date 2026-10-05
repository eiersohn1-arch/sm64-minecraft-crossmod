#!/usr/bin/env python3
"""Generate the first SM64 host adapter from a clean sm64-port checkout.

The WebSocket transport is copied verbatim from Universal Modder.  This file
only adds the thin SM64-specific pose adapter and lifecycle calls.
"""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
UM=ROOT/"vendor"/"universal-modder"
SM64=ROOT/"vendor"/"sm64-port"
REF=UM/"examples"/"minecraft-gta5-passthrough"/"gta"/"src"

if not (SM64/"src"/"game"/"game_init.c").is_file():
    raise SystemExit("Run setup-windows.bat first.")

bridge=SM64/"src"/"pc"/"universal_modder"
bridge.mkdir(parents=True,exist_ok=True)
for name in ("ws.cpp","ws.h"):
    shutil.copy2(REF/name,bridge/name)

(bridge/"sm64_passthrough.h").write_text(r'''#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void um_passthrough_start(void);
void um_passthrough_stop(void);
void um_passthrough_frame(void);
#ifdef __cplusplus
}
#endif
''',encoding="utf-8")

(bridge/"sm64_passthrough.cpp").write_text(r'''#include "sm64_passthrough.h"
#include "ws.h"
#include <cstdio>
#include <string>
extern "C" {
#include "game/camera.h"
#include "game/mario.h"
#include "game/level_update.h"
}

static WsClient s_ws;
static unsigned long long s_frame;

void um_passthrough_start(void) {
    s_ws.start("127.0.0.1", 25599);
}
void um_passthrough_stop(void) {
    s_ws.stop();
}
void um_passthrough_frame(void) {
    if (!s_ws.connected() || gMarioState == nullptr) return;
    // Minimal milestone: prove the real SM64 runtime drives the real UM Minecraft guest.
    // Scale is intentionally isolated here; later collision/render milestones share this transform.
    constexpr float S = 100.0f;
    const float x = gLakituState.pos[0] / S;
    const float y = gLakituState.pos[1] / S + 64.0f;
    const float z = -gLakituState.pos[2] / S;
    const float px = gMarioState->pos[0] / S;
    const float py = gMarioState->pos[1] / S + 64.0f;
    const float pz = -gMarioState->pos[2] / S;
    const float yaw = 180.0f - (float)gMarioState->faceAngle[1] * (360.0f / 65536.0f);
    char msg[512];
    std::snprintf(msg,sizeof(msg),
      "{\"t\":\"cam\",\"f\":%llu,\"p\":[%.4f,%.4f,%.4f],\"r\":[%.3f,0,0],\"fov\":60,\"fp\":false,\"pl\":[%.4f,%.4f,%.4f],\"h\":%.3f}",
      ++s_frame,x,y,z,yaw,px,py,pz,yaw);
    s_ws.send(msg);
}
''',encoding="utf-8")

print("Generated clean SM64 Universal Modder host adapter:",bridge)
print("NOTE: source generation is complete; sm64-port build integration is the next milestone.")
