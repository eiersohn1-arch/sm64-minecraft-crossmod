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
SM64 = ROOT / "vendor" / "sm64coopdx"
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
    "            um_passthrough_sync_health(gMarioState);\n"
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


# Minecraft blocks are real collision for the SM64 side too.  This ports the
# dynamic-surface half of the earlier bridge, but keeps Universal Modder's
# Minecraft guest as the source of truth for blocks.
object_list_processor = SM64 / "src" / "game" / "object_list_processor.c"
surface_load_h = SM64 / "src" / "engine" / "surface_load.h"
surface_load_c = SM64 / "src" / "engine" / "surface_load.c"

patch_once(
    object_list_processor,
    '#include "platform_displacement.h"\n',
    '#include "platform_displacement.h"\n#include "pc/sm64_passthrough.h"\n',
)
patch_once(
    object_list_processor,
    "    update_terrain_objects();\n\n"
    "    // If Mario was touching a moving platform",
    "    update_terrain_objects();\n"
    "    um_passthrough_load_block_surfaces();\n\n"
    "    // If Mario was touching a moving platform",
)

patch_once(
    surface_load_h,
    "void load_object_collision_model(void);\n",
    "void load_object_collision_model(void);\n"
    "void crossmod_add_dynamic_box(\n"
    "    s16 minX, s16 minY, s16 minZ,\n"
    "    s16 maxX, s16 maxY, s16 maxZ\n"
    ");\n",
)

surface_text = surface_load_c.read_text(encoding="utf-8")
if "void crossmod_add_dynamic_box(" not in surface_text:
    surface_text += r"""

/*
 * Universal Modder Minecraft block collision.
 *
 * Each Minecraft block is turned into a native SM64 dynamic collision box
 * after normal moving-platform collision is loaded for the frame.
 */
static void crossmod_add_dynamic_triangle(
        s16 x1, s16 y1, s16 z1,
        s16 x2, s16 y2, s16 z2,
        s16 x3, s16 y3, s16 z3
) {
    s16 vertexData[9] = {
        x1, y1, z1,
        x2, y2, z2,
        x3, y3, z3
    };
    s16 indices[3] = { 0, 1, 2 };
    s16 *cursor = indices;

    struct Surface *surface = read_surface_data(vertexData, &cursor, SURFACE_POOL_DYNAMIC);
    if (surface == NULL) {
        return;
    }

    surface->type = SURFACE_DEFAULT;
    surface->flags |= SURFACE_FLAG_DYNAMIC;
    surface->room = 0;
    surface->object = NULL;
    add_surface(surface);
}

void crossmod_add_dynamic_box(
        s16 x0, s16 y0, s16 z0,
        s16 x1, s16 y1, s16 z1
) {
    if (x0 >= x1 || y0 >= y1 || z0 >= z1) {
        return;
    }

    crossmod_add_dynamic_triangle(x0,y0,z0, x1,y0,z0, x1,y0,z1);
    crossmod_add_dynamic_triangle(x0,y0,z0, x1,y0,z1, x0,y0,z1);

    crossmod_add_dynamic_triangle(x0,y1,z0, x1,y1,z1, x1,y1,z0);
    crossmod_add_dynamic_triangle(x0,y1,z0, x0,y1,z1, x1,y1,z1);

    crossmod_add_dynamic_triangle(x0,y0,z0, x0,y1,z0, x1,y1,z0);
    crossmod_add_dynamic_triangle(x0,y0,z0, x1,y1,z0, x1,y0,z0);

    crossmod_add_dynamic_triangle(x0,y0,z1, x1,y0,z1, x1,y1,z1);
    crossmod_add_dynamic_triangle(x0,y0,z1, x1,y1,z1, x0,y1,z1);

    crossmod_add_dynamic_triangle(x0,y0,z0, x0,y0,z1, x0,y1,z1);
    crossmod_add_dynamic_triangle(x0,y0,z0, x0,y1,z1, x0,y1,z0);

    crossmod_add_dynamic_triangle(x1,y0,z0, x1,y1,z0, x1,y1,z1);
    crossmod_add_dynamic_triangle(x1,y0,z0, x1,y1,z1, x1,y0,z1);
}
"""
    surface_load_c.write_text(surface_text, encoding="utf-8")


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

# Lifecycle in SM64CoopDX. Minecraft is polled once per gameplay update;
# the D3D11 compositor may still draw multiple interpolated CoopDX frames.
pc_main = PC / "pc_main.c"
patch_once(
    pc_main,
    '#include "configfile.h"\n',
    '#include "configfile.h"\n#include "sm64_passthrough.h"\n',
)
patch_once(
    pc_main,
    "    CTX_EXTENT(CTX_GAME_LOOP, game_loop_one_iteration);\n",
    "    um_passthrough_before_frame();\n"
    "    CTX_EXTENT(CTX_GAME_LOOP, game_loop_one_iteration);\n"
    "    um_passthrough_frame();\n",
)
patch_once(
    pc_main,
    '        gfx_init(gWindowApi, gRenderApi, TITLE);\n',
    '        gfx_init(gWindowApi, gRenderApi, TITLE);\n'
    '        um_passthrough_start();\n'
    '        atexit(um_passthrough_stop);\n',
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

# Real raw mouse + event-driven keys from the SM64CoopDX DXGI window.
dxgi = GFX / "gfx_dxgi.cpp"
patch_once(
    dxgi,
    '#include "gfx_pc.h"\n',
    '#include "gfx_pc.h"\n#include "../sm64_passthrough.h"\n',
)
patch_once(
    dxgi,
    "        case WM_SIZE: {\n"
    "            gfx_dxgi_on_resize();\n"
    "            return 0;\n"
    "        }\n",
    "        case WM_SIZE: {\n"
    "            gfx_dxgi_on_resize();\n"
    "            if (LOWORD(l_param) >= 320 && HIWORD(l_param) >= 240) {\n"
    "                um_passthrough_view((int)LOWORD(l_param), (int)HIWORD(l_param));\n"
    "            }\n"
    "            return 0;\n"
    "        }\n",
)
patch_once(
    dxgi,
    "        case WM_ACTIVATEAPP: {\n"
    "            if (dxgi.on_all_keys_up != nullptr) {\n",
    "        case WM_ACTIVATEAPP: {\n"
    "            um_passthrough_focus_changed(w_param != 0);\n"
    "            if (dxgi.on_all_keys_up != nullptr) {\n",
)
patch_once(
    dxgi,
    "        case WM_KEYDOWN: {\n"
    "            gfx_dxgi_on_key_down(w_param, l_param);\n",
    "        case WM_KEYDOWN: {\n"
    "            um_passthrough_key_event((int)w_param, 1);\n"
    "            gfx_dxgi_on_key_down(w_param, l_param);\n",
)
patch_once(
    dxgi,
    "        case WM_KEYUP: {\n"
    "            gfx_dxgi_on_key_up(w_param, l_param);\n",
    "        case WM_KEYUP: {\n"
    "            um_passthrough_key_event((int)w_param, 0);\n"
    "            gfx_dxgi_on_key_up(w_param, l_param);\n",
)
patch_once(
    dxgi,
    "        case WM_MOUSEWHEEL: {\n"
    "            gfx_dxgi_on_scroll(w_param);\n",
    "        case WM_MOUSEMOVE: {\n"
    "            RECT client{};\n"
    "            if (GetClientRect(h_wnd, &client)) {\n"
    "                um_passthrough_pointer((int)(short)LOWORD(l_param), (int)(short)HIWORD(l_param),\n"
    "                    client.right - client.left, client.bottom - client.top);\n"
    "            }\n"
    "            return 0;\n"
    "        }\n"
    "        case WM_MOUSEWHEEL: {\n"
    "            um_passthrough_scroll(GET_WHEEL_DELTA_WPARAM(w_param));\n"
    "            gfx_dxgi_on_scroll(w_param);\n",
)
patch_once(
    dxgi,
    "        case WM_LBUTTONDOWN: {\n"
    "            if (!gRomIsValid) {\n",
    "        case WM_LBUTTONDOWN: {\n"
    "            um_passthrough_mouse_button(0, 1);\n"
    "            if (!gRomIsValid) {\n",
)
patch_once(
    dxgi,
    "        case WM_DROPFILES: {\n",
    "        case WM_LBUTTONUP: {\n"
    "            um_passthrough_mouse_button(0, 0);\n"
    "            return 0;\n"
    "        }\n"
    "        case WM_RBUTTONDOWN: {\n"
    "            um_passthrough_mouse_button(1, 1);\n"
    "            return 0;\n"
    "        }\n"
    "        case WM_RBUTTONUP: {\n"
    "            um_passthrough_mouse_button(1, 0);\n"
    "            return 0;\n"
    "        }\n"
    "        case WM_MBUTTONDOWN: {\n"
    "            um_passthrough_mouse_button(2, 1);\n"
    "            return 0;\n"
    "        }\n"
    "        case WM_MBUTTONUP: {\n"
    "            um_passthrough_mouse_button(2, 0);\n"
    "            return 0;\n"
    "        }\n"
    "        case WM_SETCURSOR: {\n"
    "            if (um_passthrough_pointer_locked() && LOWORD(l_param) == HTCLIENT) {\n"
    "                SetCursor(nullptr);\n"
    "                return TRUE;\n"
    "            }\n"
    "            break;\n"
    "        }\n"
    "        case WM_INPUT: {\n"
    "            RAWINPUT raw{};\n"
    "            UINT size = sizeof(raw);\n"
    "            if (GetRawInputData((HRAWINPUT)l_param, RID_INPUT, &raw, &size, sizeof(RAWINPUTHEADER)) == size\n"
    "                && raw.header.dwType == RIM_TYPEMOUSE) {\n"
    "                um_passthrough_raw_mouse(raw.data.mouse.lLastX, raw.data.mouse.lLastY);\n"
    "            }\n"
    "            return 0;\n"
    "        }\n"
    "        case WM_DROPFILES: {\n",
)
patch_once(
    dxgi,
    "    });\n\n"
    "    load_dxgi_library();\n",
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
    "  BACKEND_LDFLAGS += -ld3dcompiler -ldxgi -ldxguid\n",
    "  BACKEND_LDFLAGS += -ld3dcompiler -ldxgi -ldxguid -lws2_32 -pthread\n",
)

print("Installed real Universal Modder Minecraft passthrough into SM64CoopDX.")
print("  guest: Universal Modder minecraft-gta5-passthrough/mc")
print("  transport: Universal Modder ws.cpp/ws.h")
print("  input: SM64 Win32 raw input -> real Minecraft key mappings")
print("  collision: SM64 surfaces -> Minecraft, Minecraft blocks -> native SM64 dynamic surfaces")
print("  render: MCPT world depth-tested against SM64 + HUD overlay")
