#!/usr/bin/env python3
"""Install the modular one-process Minecraft runtime into a clean sm64-port.

Universal Modder mashup Pattern 4: reimplement, then fuse.
The real C++ sources live in native_runtime/. This script only copies them into
sm64-port and installs the small host hooks required by the fusion.
"""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SM64 = ROOT / "vendor" / "sm64-port"
RUNTIME = ROOT / "native_runtime"
PC = SM64 / "src" / "pc"
NM = PC / "native_minecraft"
GFX = PC / "gfx"


def patch_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch marker missing in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


required = [
    RUNTIME / "native_minecraft.h",
    RUNTIME / "native_minecraft_internal.h",
    RUNTIME / "input.cpp",
    RUNTIME / "world.cpp",
    RUNTIME / "player.cpp",
    RUNTIME / "bridge.cpp",
    RUNTIME / "native_minecraft_render.inc",
    SM64 / "Makefile",
    SM64 / "src" / "game" / "mario.c",
    SM64 / "src" / "game" / "camera.c",
    SM64 / "src" / "game" / "hud.c",
    GFX / "gfx_dxgi.cpp",
    GFX / "gfx_direct3d11.cpp",
]
missing = [str(p) for p in required if not p.is_file()]
if missing:
    raise SystemExit("Native fusion prerequisites missing: " + ", ".join(missing))

if NM.exists():
    shutil.rmtree(NM)
NM.mkdir(parents=True)

for name in [
    "native_minecraft.h",
    "native_minecraft_internal.h",
    "input.cpp",
    "world.cpp",
    "player.cpp",
    "bridge.cpp",
]:
    shutil.copy2(RUNTIME / name, NM / name)

shutil.copy2(
    RUNTIME / "native_minecraft_render.inc",
    GFX / "native_minecraft_render.inc",
)

# sm64-port only scans explicitly listed source directories. Add the native
# module directory so the real make build compiles and links every V2 module.
makefile = SM64 / "Makefile"
patch_once(
    makefile,
    "  SRC_DIRS += src/pc src/pc/gfx src/pc/audio src/pc/controller\n",
    "  SRC_DIRS += src/pc src/pc/gfx src/pc/audio src/pc/controller src/pc/native_minecraft\n",
)

# Mario keeps its original state machine for triggers/cutscenes, but its normal
# controller is neutralized while the native runtime owns locomotion.
mario = SM64 / "src" / "game" / "mario.c"
patch_once(
    mario,
    '#include "rumble_init.h"\n',
    '#include "rumble_init.h"\n#include "pc/native_minecraft/native_minecraft.h"\n',
)
patch_once(
    mario,
    "        mario_reset_bodystate(gMarioState);\n"
    "        update_mario_inputs(gMarioState);\n",
    "        mario_reset_bodystate(gMarioState);\n"
    "        native_minecraft_pre_mario_action(gMarioState);\n"
    "        update_mario_inputs(gMarioState);\n",
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
    "        if (native_minecraft_has_authority()) {\n"
    "            gMarioState->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;\n"
    "        }\n",
)

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
    "    if (native_minecraft_has_authority()) return;\n"
    "    s16 hudDisplayFlags;\n",
)

# Raw Win32 input arrives at message-pump speed rather than SM64 game-tick speed.
dxgi = GFX / "gfx_dxgi.cpp"
patch_once(
    dxgi,
    '#include "gfx_pc.h"\n',
    '#include "gfx_pc.h"\n#include "native_minecraft/native_minecraft.h"\n',
)
patch_once(
    dxgi,
    "        case WM_ACTIVATEAPP:\n"
    "            if (dxgi.on_all_keys_up != nullptr) {\n",
    "        case WM_ACTIVATEAPP:\n"
    "            native_minecraft_focus_changed(w_param != 0);\n"
    "            if (dxgi.on_all_keys_up != nullptr) {\n",
)
patch_once(
    dxgi,
    "        case WM_KEYDOWN:\n"
    "            onkeydown(w_param, l_param);\n"
    "            break;\n"
    "        case WM_KEYUP:\n"
    "            onkeyup(w_param, l_param);\n"
    "            break;\n",
    "        case WM_KEYDOWN:\n"
    "            native_minecraft_key_event((int)w_param, 1);\n"
    "            onkeydown(w_param, l_param);\n"
    "            break;\n"
    "        case WM_KEYUP:\n"
    "            native_minecraft_key_event((int)w_param, 0);\n"
    "            onkeyup(w_param, l_param);\n"
    "            break;\n"
    "        case WM_LBUTTONDOWN:\n"
    "            native_minecraft_mouse_button(0, 1);\n"
    "            break;\n"
    "        case WM_LBUTTONUP:\n"
    "            native_minecraft_mouse_button(0, 0);\n"
    "            break;\n"
    "        case WM_RBUTTONDOWN:\n"
    "            native_minecraft_mouse_button(1, 1);\n"
    "            break;\n"
    "        case WM_RBUTTONUP:\n"
    "            native_minecraft_mouse_button(1, 0);\n"
    "            break;\n"
    "        case WM_MBUTTONDOWN:\n"
    "            native_minecraft_mouse_button(2, 1);\n"
    "            break;\n"
    "        case WM_MBUTTONUP:\n"
    "            native_minecraft_mouse_button(2, 0);\n"
    "            break;\n"
    "        case WM_INPUT: {\n"
    "            RAWINPUT raw{};\n"
    "            UINT size = sizeof(raw);\n"
    "            if (GetRawInputData((HRAWINPUT)l_param, RID_INPUT, &raw, &size,\n"
    "                                sizeof(RAWINPUTHEADER)) == size\n"
    "                && raw.header.dwType == RIM_TYPEMOUSE) {\n"
    "                native_minecraft_raw_mouse(\n"
    "                    raw.data.mouse.lLastX, raw.data.mouse.lLastY);\n"
    "            }\n"
    "            break;\n"
    "        }\n",
)
patch_once(
    dxgi,
    "        dxgi.h_wnd = CreateWindowW(WINCLASS_NAME, w_title, WS_OVERLAPPEDWINDOW,\n"
    "            CW_USEDEFAULT, 0, wr.right - wr.left, wr.bottom - wr.top, nullptr, nullptr, nullptr, nullptr);\n"
    "    });\n\n"
    "    load_dxgi_library();\n",
    "        dxgi.h_wnd = CreateWindowW(WINCLASS_NAME, w_title, WS_OVERLAPPEDWINDOW,\n"
    "            CW_USEDEFAULT, 0, wr.right - wr.left, wr.bottom - wr.top, nullptr, nullptr, nullptr, nullptr);\n"
    "    });\n\n"
    "    RAWINPUTDEVICE nativeMouse{};\n"
    "    nativeMouse.usUsagePage = 0x01;\n"
    "    nativeMouse.usUsage = 0x02;\n"
    "    nativeMouse.dwFlags = 0;\n"
    "    nativeMouse.hwndTarget = dxgi.h_wnd;\n"
    "    RegisterRawInputDevices(&nativeMouse, 1, sizeof(nativeMouse));\n\n"
    "    load_dxgi_library();\n",
)

d3d = GFX / "gfx_direct3d11.cpp"
patch_once(
    d3d,
    "#include <cstdio>\n#include <vector>\n#include <cmath>\n",
    "#include <cstdio>\n#include <vector>\n#include <cmath>\n"
    "#include <algorithm>\n#include <cstring>\n"
    '#include "native_minecraft/native_minecraft.h"\n',
)
patch_once(
    d3d,
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
    '#include "native_minecraft_render.inc"\n\n'
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
)
patch_once(
    d3d,
    "static void gfx_d3d11_end_frame(void) {\n}\n",
    "static void gfx_d3d11_end_frame(void) {\n"
    "    nm_render_native_minecraft();\n"
    "}\n",
)

print("Installed modular Native Minecraft V2 into:", NM)
print("  modules: input / player / world / bridge")
print("  renderer: depth-aware world pass + independent HUD/inventory pass")
print("  input: Win32 raw mouse + event-driven keys/buttons")
print("  transport: none (single process)")
