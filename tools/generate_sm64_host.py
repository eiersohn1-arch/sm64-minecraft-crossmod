#!/usr/bin/env python3
"""Install the tracked SM64 host adapter for Universal Modder Pattern 2.

The Minecraft side remains the real Universal Modder passthrough guest.
This script only copies the tracked SM64 adapter and installs the minimal host
hooks into a clean sm64-port checkout.
"""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
UM = ROOT / "vendor" / "universal-modder"
SM64 = ROOT / "vendor" / "sm64-port"
ADAPTER = ROOT / "host_adapter"
REF = UM / "examples" / "minecraft-gta5-passthrough" / "gta" / "src"
PC = SM64 / "src" / "pc"
GFX = PC / "gfx"


def patch_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch marker missing in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


required = [
    SM64 / "src" / "game" / "game_init.c",
    REF / "ws.cpp",
    REF / "ws.h",
    ADAPTER / "sm64_passthrough.h",
    ADAPTER / "sm64_passthrough.cpp",
    ADAPTER / "um_mcpt_overlay.inc",
]
missing = [str(p) for p in required if not p.is_file()]
if missing:
    raise SystemExit("Passthrough prerequisites missing: " + ", ".join(missing))

# Transport is copied verbatim from Universal Modder.
shutil.copy2(REF / "ws.cpp", PC / "ws.cpp")
shutil.copy2(REF / "ws.h", PC / "ws.h")

# The SM64-specific glue is tracked directly in this repo.
shutil.copy2(ADAPTER / "sm64_passthrough.h", PC / "sm64_passthrough.h")
shutil.copy2(ADAPTER / "sm64_passthrough.cpp", PC / "sm64_passthrough.cpp")
shutil.copy2(ADAPTER / "um_mcpt_overlay.inc", GFX / "um_mcpt_overlay.inc")

# Mario keeps its mission/interaction state machine, but while Minecraft owns
# locomotion the ordinary SM64 controller is neutralized before action logic.
mario = SM64 / "src" / "game" / "mario.c"
patch_once(
    mario,
    '#include "rumble_init.h"\n',
    '#include "rumble_init.h"\n#include "pc/sm64_passthrough.h"\n',
)
patch_once(
    mario,
    "        mario_reset_bodystate(gMarioState);\n"
    "        update_mario_inputs(gMarioState);\n",
    "        mario_reset_bodystate(gMarioState);\n"
    "        if (um_passthrough_minecraft_authority()) {\n"
    "            um_passthrough_apply_mario_proxy(gMarioState);\n"
    "        }\n"
    "        um_passthrough_neutralize_controller(gMarioState);\n"
    "        update_mario_inputs(gMarioState);\n",
)
patch_once(
    mario,
    "        update_mario_health(gMarioState);\n"
    "        update_mario_info_for_cam(gMarioState);\n",
    "        update_mario_health(gMarioState);\n"
    "        if (um_passthrough_minecraft_authority()) {\n"
    "            um_passthrough_apply_mario_proxy(gMarioState);\n"
    "        }\n"
    "        update_mario_info_for_cam(gMarioState);\n",
)
patch_once(
    mario,
    "        mario_update_hitbox_and_cap_model(gMarioState);\n",
    "        mario_update_hitbox_and_cap_model(gMarioState);\n"
    "        if (um_passthrough_connected()) {\n"
    "            gMarioState->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;\n"
    "        }\n",
)

# Minecraft renders the visible survival HUD while attached.
hud = SM64 / "src" / "game" / "hud.c"
patch_once(
    hud,
    '#include "hud.h"\n',
    '#include "hud.h"\n#include "pc/sm64_passthrough.h"\n',
)
patch_once(
    hud,
    "void render_hud(void) {\n"
    "    s16 hudDisplayFlags;\n",
    "void render_hud(void) {\n"
    "    if (um_passthrough_connected()) return;\n"
    "    s16 hudDisplayFlags;\n",
)

# Normal gameplay uses Minecraft's real camera. SM64 cutscenes keep Lakitu;
# the Minecraft guest follows that host camera in non-drive mode.
camera = SM64 / "src" / "game" / "camera.c"
patch_once(
    camera,
    '#include "level_table.h"\n',
    '#include "level_table.h"\n#include "pc/sm64_passthrough.h"\n',
)
patch_once(
    camera,
    "    update_lakitu(c);\n\n"
    "    gLakituState.lastFrameAction = sMarioCamState->action;\n",
    "    update_lakitu(c);\n"
    "    um_passthrough_override_camera();\n\n"
    "    gLakituState.lastFrameAction = sMarioCamState->action;\n",
)

# Lifecycle in the real SM64 executable.
pc_main = PC / "pc_main.c"
patch_once(
    pc_main,
    '#include "configfile.h"\n',
    '#include "configfile.h"\n#include "sm64_passthrough.h"\n',
)
patch_once(
    pc_main,
    "    gfx_start_frame();\n"
    "    game_loop_one_iteration();\n",
    "    gfx_start_frame();\n"
    "    um_passthrough_before_frame();\n"
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

# Draw Universal Modder's world/depth/overlay shared-memory frame inside SM64.
gfx = GFX / "gfx_direct3d11.cpp"
patch_once(
    gfx,
    "#include <cstdio>\n",
    "#include <cstdio>\n#include <cstring>\n"
    '#include "../sm64_passthrough.h"\n',
)
patch_once(
    gfx,
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
    '#include "um_mcpt_overlay.inc"\n\n'
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
)
patch_once(
    gfx,
    "static void gfx_d3d11_end_frame(void) {\n}\n",
    "static void gfx_d3d11_end_frame(void) {\n"
    "    um_draw_mcpt();\n"
    "}\n",
)

# Real raw mouse + event-driven keys from the SM64 DXGI window.
dxgi = GFX / "gfx_dxgi.cpp"
patch_once(
    dxgi,
    '#include "gfx_pc.h"\n',
    '#include "gfx_pc.h"\n#include "../sm64_passthrough.h"\n',
)
patch_once(
    dxgi,
    "        case WM_ACTIVATEAPP:\n"
    "            if (dxgi.on_all_keys_up != nullptr) {\n",
    "        case WM_ACTIVATEAPP:\n"
    "            um_passthrough_focus_changed(w_param != 0);\n"
    "            if (dxgi.on_all_keys_up != nullptr) {\n",
)
patch_once(
    dxgi,
    "        case WM_SIZE:\n"
    "            gfx_dxgi_on_resize();\n"
    "            break;\n",
    "        case WM_SIZE:\n"
    "            gfx_dxgi_on_resize();\n"
    "            if (LOWORD(l_param) >= 320 && HIWORD(l_param) >= 240) {\n"
    "                um_passthrough_view((int)LOWORD(l_param), (int)HIWORD(l_param));\n"
    "            }\n"
    "            break;\n",
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
    "            um_passthrough_key_event((int)w_param, 1);\n"
    "            onkeydown(w_param, l_param);\n"
    "            break;\n"
    "        case WM_KEYUP:\n"
    "            um_passthrough_key_event((int)w_param, 0);\n"
    "            onkeyup(w_param, l_param);\n"
    "            break;\n"
    "        case WM_MOUSEMOVE: {\n"
    "            RECT client{};\n"
    "            if (GetClientRect(h_wnd, &client)) {\n"
    "                int x = (int)(short)LOWORD(l_param);\n"
    "                int y = (int)(short)HIWORD(l_param);\n"
    "                um_passthrough_pointer(x, y, client.right - client.left, client.bottom - client.top);\n"
    "            }\n"
    "            break;\n"
    "        }\n"
    "        case WM_LBUTTONDOWN:\n"
    "            um_passthrough_mouse_button(0, 1);\n"
    "            break;\n"
    "        case WM_LBUTTONUP:\n"
    "            um_passthrough_mouse_button(0, 0);\n"
    "            break;\n"
    "        case WM_RBUTTONDOWN:\n"
    "            um_passthrough_mouse_button(1, 1);\n"
    "            break;\n"
    "        case WM_RBUTTONUP:\n"
    "            um_passthrough_mouse_button(1, 0);\n"
    "            break;\n"
    "        case WM_MBUTTONDOWN:\n"
    "            um_passthrough_mouse_button(2, 1);\n"
    "            break;\n"
    "        case WM_MBUTTONUP:\n"
    "            um_passthrough_mouse_button(2, 0);\n"
    "            break;\n"
    "        case WM_MOUSEWHEEL:\n"
    "            um_passthrough_scroll(GET_WHEEL_DELTA_WPARAM(w_param));\n"
    "            break;\n"
    "        case WM_SETCURSOR:\n"
    "            if (um_passthrough_pointer_locked() && LOWORD(l_param) == HTCLIENT) {\n"
    "                SetCursor(nullptr);\n"
    "                return TRUE;\n"
    "            }\n"
    "            return DefWindowProcW(h_wnd, message, w_param, l_param);\n"
    "        case WM_INPUT: {\n"
    "            RAWINPUT raw{};\n"
    "            UINT size = sizeof(raw);\n"
    "            if (GetRawInputData((HRAWINPUT)l_param, RID_INPUT, &raw, &size,\n"
    "                                sizeof(RAWINPUTHEADER)) == size\n"
    "                && raw.header.dwType == RIM_TYPEMOUSE) {\n"
    "                um_passthrough_raw_mouse(raw.data.mouse.lLastX, raw.data.mouse.lLastY);\n"
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
    "    RAWINPUTDEVICE rawMouse{};\n"
    "    rawMouse.usUsagePage = 0x01;\n"
    "    rawMouse.usUsage = 0x02;\n"
    "    rawMouse.dwFlags = 0;\n"
    "    rawMouse.hwndTarget = dxgi.h_wnd;\n"
    "    RegisterRawInputDevices(&rawMouse, 1, sizeof(rawMouse));\n\n"
    "    load_dxgi_library();\n",
)

# Universal Modder's websocket client uses Winsock and a worker thread.
makefile = SM64 / "Makefile"
patch_once(
    makefile,
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -no-pie -mwindows",
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -pthread -no-pie -mwindows",
)

print("Installed real Universal Modder Minecraft passthrough into SM64.")
print("  guest: Universal Modder minecraft-gta5-passthrough/mc")
print("  transport: Universal Modder ws.cpp/ws.h")
print("  input: SM64 Win32 raw input -> real Minecraft key mappings")
print("  collision: SM64 floor/ceiling/wall barriers -> Minecraft")
print("  render: MCPT world depth-tested against SM64 + HUD overlay")
