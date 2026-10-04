#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
ROM = ROOT / "rom" / "baserom.us.z64"
SM64_PORT = VENDOR / "sm64-port"
UNIVERSAL_MODDER = VENDOR / "universal-modder"

EXPECTED_SHA1 = "9bef1128717f958171a4afac3ed78ee2bb4e86ce"


def run(args: list[str], cwd: pathlib.Path | None = None) -> None:
    print("+", " ".join(str(part) for part in args))
    subprocess.run(args, cwd=cwd, check=True)


def sha1(path: pathlib.Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_rom() -> None:
    if not ROM.is_file():
        raise RuntimeError(f"ROM missing: {ROM}")

    digest = sha1(ROM)
    if digest.lower() != EXPECTED_SHA1:
        raise RuntimeError(
            "Wrong ROM. Expected clean Super Mario 64 (USA) .z64 "
            f"with SHA-1 {EXPECTED_SHA1}; got {digest}"
        )


def clone_if_missing(url: str, target: pathlib.Path) -> None:
    if (target / ".git").is_dir():
        print(f"OK: {target.name} already cloned.")
        return

    if target.exists():
        raise RuntimeError(
            f"{target} exists but is not a Git checkout."
        )

    run(["git", "clone", "--depth", "1", url, str(target)])


def patch_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")

    if new in text:
        return

    if old not in text:
        raise RuntimeError(
            f"Could not patch {path}: expected source marker not found."
        )

    path.write_text(
        text.replace(old, new, 1),
        encoding="utf-8",
    )


def patch_all(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")

    if old not in text:
        if new in text:
            return
        raise RuntimeError(
            f"Could not patch {path}: expected source marker not found."
        )

    path.write_text(
        text.replace(old, new),
        encoding="utf-8",
    )


def patch_sm64_port_toolchain() -> None:
    """Patch old bundled build tools for current MSYS2/GCC releases."""
    armips = SM64_PORT / "tools" / "armips.cpp"

    if not armips.is_file():
        raise RuntimeError(f"Bundled armips source missing: {armips}")

    # The old sm64-port armips amalgamation relies on int64_t arriving through
    # transitive headers. Modern MinGW/GCC can encounter SymbolTable.h before
    # int64_t is declared, recover it as the wrong parameter type, and later
    # reject SymbolTable::findSection(int64_t). Include <cstdint> explicitly at
    # the start so the declaration and definition always use the same type.
    patch_once(
        armips,
        "#include <cstdio>\n",
        "#include <cstdint>\n#include <cstdio>\n",
    )

    # The bundled armips uses std::wstring paths but calls the generic Win32
    # GetFileAttributes* macros. With current MinGW those macros resolve to
    # the ANSI A variants unless UNICODE is globally defined, which rejects
    # wchar_t*. Call the wide W variants explicitly instead.
    patch_once(
        armips,
        "GetFileAttributesEx(fileName.c_str(),GetFileExInfoStandard,&attr)",
        "GetFileAttributesExW(fileName.c_str(),GetFileExInfoStandard,&attr)",
    )
    patch_all(
        armips,
        "GetFileAttributes(strFilename.c_str())",
        "GetFileAttributesW(strFilename.c_str())",
    )

    print("Patched bundled armips for modern MSYS2/GCC.")


def install_bridge() -> None:
    shutil.copy2(
        ROOT / "sm64-host" / "crossmod_bridge.c",
        SM64_PORT / "src" / "pc" / "crossmod_bridge.c",
    )
    shutil.copy2(
        ROOT / "sm64-host" / "crossmod_bridge.h",
        SM64_PORT / "src" / "pc" / "crossmod_bridge.h",
    )
    shutil.copy2(
        ROOT / "sm64-host" / "crossmod_ws_api.h",
        SM64_PORT / "src" / "pc" / "crossmod_ws_api.h",
    )
    shutil.copy2(
        ROOT / "sm64-host" / "crossmod_ws_api.cpp",
        SM64_PORT / "src" / "pc" / "crossmod_ws_api.cpp",
    )

    # Use the WebSocket implementation directly from the exact
    # universal-modder clone requested by the project owner.
    universal_ws = (
        UNIVERSAL_MODDER
        / "examples"
        / "minecraft-gta5-passthrough"
        / "gta"
        / "src"
    )
    shutil.copy2(
        universal_ws / "ws.h",
        SM64_PORT / "src" / "pc" / "ws.h",
    )
    shutil.copy2(
        universal_ws / "ws.cpp",
        SM64_PORT / "src" / "pc" / "ws.cpp",
    )
    shutil.copy2(
        ROOT / "sm64-host" / "mc_overlay_dx11.inc",
        SM64_PORT / "src" / "pc" / "gfx" / "mc_overlay_dx11.inc",
    )

    pc_main = SM64_PORT / "src" / "pc" / "pc_main.c"
    mario = SM64_PORT / "src" / "game" / "mario.c"
    game_init = SM64_PORT / "src" / "game" / "game_init.c"
    camera = SM64_PORT / "src" / "game" / "camera.c"
    hud = SM64_PORT / "src" / "game" / "hud.c"
    object_list_processor = (
        SM64_PORT / "src" / "game" / "object_list_processor.c"
    )
    surface_load_h = (
        SM64_PORT / "src" / "engine" / "surface_load.h"
    )
    surface_load_c = (
        SM64_PORT / "src" / "engine" / "surface_load.c"
    )
    makefile = SM64_PORT / "Makefile"
    gfx_d3d11 = SM64_PORT / "src" / "pc" / "gfx" / "gfx_direct3d11.cpp"
    gfx_sdl2 = SM64_PORT / "src" / "pc" / "gfx" / "gfx_sdl2.c"

    # Migrate vendor/sm64-port checkouts that were patched by the older
    # position-authority bridge. setup-windows.bat intentionally reuses the
    # existing vendor checkout, so an old crossmod_bridge_apply_mario() block
    # can survive a git pull even though the current bridge no longer defines
    # that function. Restore vanilla execute_mario_action() before installing
    # the new native-authority controller bridge.
    mario_text = mario.read_text(encoding="utf-8")
    legacy_mario_block = (
        "    if (gMarioState->action) {\n"
        "        if (crossmod_bridge_apply_mario(gMarioState)) {\n"
        "            gMarioState->marioObj->header.gfx.node.flags |= GRAPH_RENDER_INVISIBLE;\n"
        "            mario_reset_bodystate(gMarioState);\n"
        "            mario_handle_special_floors(gMarioState);\n"
        "            mario_process_interactions(gMarioState);\n"
        "            gMarioState->marioObj->oInteractStatus = 0;\n"
        "            return 0;\n"
        "        }\n"
        "        gMarioState->marioObj->header.gfx.node.flags &= ~GRAPH_RENDER_INVISIBLE;\n"
        "        mario_reset_bodystate(gMarioState);"
    )
    vanilla_mario_block = (
        "    if (gMarioState->action) {\n"
        "        gMarioState->marioObj->header.gfx.node.flags &= ~GRAPH_RENDER_INVISIBLE;\n"
        "        mario_reset_bodystate(gMarioState);"
    )

    if legacy_mario_block in mario_text:
        mario.write_text(
            mario_text.replace(legacy_mario_block, vanilla_mario_block, 1),
            encoding="utf-8",
        )
        print("Migrated old crossmod_bridge_apply_mario patch.")

    # Migrate checkouts patched by the short-lived full execute_mario_action
    # bypass. That version skipped entire native action groups and could leave
    # stars/doors/cutscenes or the player state stuck. Restore the ordinary
    # action loop, then install the safer position-only proxy hooks below.
    mario_text = mario.read_text(encoding="utf-8")
    locomotion_bypass_marker = (
        "    /*\n"
        "     * Crossmod locomotion mode: vanilla Minecraft owns all player\n"
    )
    if locomotion_bypass_marker in mario_text:
        bypass_start = mario_text.index(locomotion_bypass_marker)
        vanilla_resume = mario_text.find(
            "    if (gMarioState->action) {",
            bypass_start,
        )
        if vanilla_resume < 0:
            raise RuntimeError(
                "Could not migrate the old locomotion bypass in mario.c"
            )

        mario.write_text(
            mario_text[:bypass_start] + mario_text[vanilla_resume:],
            encoding="utf-8",
        )
        print("Migrated old full locomotion bypass.")

    # Older passthrough runs inserted only the post-Mario callback. Normalize
    # that ending so it can be upgraded to the new snap-back hook idempotently.
    mario_text = mario.read_text(encoding="utf-8")
    old_after_hook = (
        "        play_infinite_stairs_music();\n"
        "        crossmod_bridge_after_mario_update(gMarioState);\n"
        "        gMarioState->marioObj->oInteractStatus = 0;"
    )
    vanilla_after_hook = (
        "        play_infinite_stairs_music();\n"
        "        gMarioState->marioObj->oInteractStatus = 0;"
    )
    if old_after_hook in mario_text:
        mario.write_text(
            mario_text.replace(
                old_after_hook,
                vanilla_after_hook,
                1,
            ),
            encoding="utf-8",
        )

    patch_once(
        pc_main,
        '#include "configfile.h"\n',
        '#include "configfile.h"\n#include "crossmod_bridge.h"\n',
    )

    patch_once(
        pc_main,
        "void produce_one_frame(void) {\n    gfx_start_frame();",
        "void produce_one_frame(void) {\n"
        "    crossmod_bridge_poll();\n"
        "    gfx_start_frame();",
    )

    patch_once(
        pc_main,
        '    gfx_init(wm_api, rendering_api, "Super Mario 64 PC-Port", configFullscreen);',
        '    gfx_init(wm_api, rendering_api, "Super Mario 64 × Minecraft", configFullscreen);\n'
        "    crossmod_bridge_init();\n"
        "    atexit(crossmod_bridge_shutdown);",
    )

    patch_once(
        mario,
        '#include "rumble_init.h"\n',
        '#include "rumble_init.h"\n#include "pc/crossmod_bridge.h"\n',
    )

    patch_once(
        mario,
        "s32 execute_mario_action(UNUSED struct Object *o) {\n"
        "    s32 inLoop = TRUE;\n\n"
        "    if (gMarioState->action) {",
        "s32 execute_mario_action(UNUSED struct Object *o) {\n"
        "    s32 inLoop = TRUE;\n\n"
        "    /* Minecraft-authoritative proxy sync (safe, non-invasive). */\n"
        "    if (crossmod_bridge_active() && gMarioState->action) {\n"
        "        crossmod_bridge_sync_minecraft_proxy(gMarioState);\n"
        "    }\n\n"
        "    if (gMarioState->action) {",
    )


    patch_once(
        camera,
        '#include "engine/surface_collision.h"\n',
        '#include "engine/surface_collision.h"\n#include "pc/crossmod_bridge.h"\n',
    )

    gfx_sdl2_text = gfx_sdl2.read_text(encoding="utf-8")
    if '#include "pc/crossmod_bridge.h"' not in gfx_sdl2_text:
        include_marker = '#include "gfx_window_manager_api.h"\n'
        if include_marker not in gfx_sdl2_text:
            raise RuntimeError(
                f"Could not patch {gfx_sdl2}: window-manager include marker not found."
            )
        gfx_sdl2.write_text(
            gfx_sdl2_text.replace(
                include_marker,
                include_marker + '#include "pc/crossmod_bridge.h"\n',
                1,
            ),
            encoding="utf-8",
        )

    patch_once(
        gfx_sdl2,
        "            case SDL_WINDOWEVENT:\n",
        "            case SDL_MOUSEWHEEL: {\n"
        "                int wheel_y = event.wheel.y;\n"
        "                if (event.wheel.direction == SDL_MOUSEWHEEL_FLIPPED) {\n"
        "                    wheel_y = -wheel_y;\n"
        "                }\n"
        "                crossmod_bridge_mouse_wheel(wheel_y);\n"
        "                break;\n"
        "            }\n"
        "            case SDL_WINDOWEVENT:\n",
    )

    patch_once(
        camera,
        "    update_lakitu(c);\n\n"
        "    gLakituState.lastFrameAction = sMarioCamState->action;",
        "    update_lakitu(c);\n"
        "    crossmod_bridge_override_camera(c);\n\n"
        "    gLakituState.lastFrameAction = sMarioCamState->action;",
    )

    patch_once(
        game_init,
        '#include "sound_init.h"\n',
        '#include "sound_init.h"\n#include "pc/crossmod_bridge.h"\n',
    )

    patch_once(
        game_init,
        "        read_controller_inputs();\n        levelCommandAddr = level_script_execute(levelCommandAddr);",
        "        read_controller_inputs();\n"
        "        crossmod_bridge_apply_controller(gPlayer1Controller);\n"
        "        levelCommandAddr = level_script_execute(levelCommandAddr);",
    )

    patch_once(
        mario,
        "        play_infinite_stairs_music();\n"
        "        gMarioState->marioObj->oInteractStatus = 0;",
        "        play_infinite_stairs_music();\n"
        "        /* Native actions may move the invisible proxy temporarily. */\n"
        "        if (crossmod_bridge_active()) {\n"
        "            crossmod_bridge_sync_minecraft_proxy(gMarioState);\n"
        "        }\n"
        "        crossmod_bridge_after_mario_update(gMarioState);\n"
        "        gMarioState->marioObj->oInteractStatus = 0;",
    )

    patch_once(
        hud,
        '#include "print.h"\n\n/* @file hud.c',
        '#include "print.h"\n#include "pc/crossmod_bridge.h"\n\n/* @file hud.c',
    )

    patch_once(
        object_list_processor,
        '#include "platform_displacement.h"\n',
        '#include "platform_displacement.h"\n'
        '#include "pc/crossmod_bridge.h"\n',
    )

    patch_once(
        object_list_processor,
        "    update_terrain_objects();\n\n"
        "    // If Mario was touching a moving platform",
        "    update_terrain_objects();\n"
        "    crossmod_bridge_load_block_surfaces();\n\n"
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
 * Crossmod collision injection.
 *
 * Minecraft remains authoritative for its blocks. Each nearby Minecraft
 * VoxelShape AABB is converted to a 12-triangle cube/rectangular prism and
 * inserted into SM64's dynamic spatial partitions after ordinary moving
 * platform collision has been loaded for the frame.
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

    struct Surface *surface =
        read_surface_data(vertexData, &cursor);

    if (surface == NULL) {
        return;
    }

    surface->type = SURFACE_DEFAULT;
    surface->flags |= SURFACE_FLAG_DYNAMIC;
    surface->room = 0;
    surface->object = NULL;

    add_surface(surface, TRUE);
}

void crossmod_add_dynamic_box(
        s16 x0, s16 y0, s16 z0,
        s16 x1, s16 y1, s16 z1
) {
    if (x0 >= x1 || y0 >= y1 || z0 >= z1) {
        return;
    }

    /* bottom -Y */
    crossmod_add_dynamic_triangle(x0,y0,z0, x1,y0,z0, x1,y0,z1);
    crossmod_add_dynamic_triangle(x0,y0,z0, x1,y0,z1, x0,y0,z1);

    /* top +Y */
    crossmod_add_dynamic_triangle(x0,y1,z0, x1,y1,z1, x1,y1,z0);
    crossmod_add_dynamic_triangle(x0,y1,z0, x0,y1,z1, x1,y1,z1);

    /* z0 face -Z */
    crossmod_add_dynamic_triangle(x0,y0,z0, x0,y1,z0, x1,y1,z0);
    crossmod_add_dynamic_triangle(x0,y0,z0, x1,y1,z0, x1,y0,z0);

    /* z1 face +Z */
    crossmod_add_dynamic_triangle(x0,y0,z1, x1,y0,z1, x1,y1,z1);
    crossmod_add_dynamic_triangle(x0,y0,z1, x1,y1,z1, x0,y1,z1);

    /* x0 face -X */
    crossmod_add_dynamic_triangle(x0,y0,z0, x0,y0,z1, x0,y1,z1);
    crossmod_add_dynamic_triangle(x0,y0,z0, x0,y1,z1, x0,y1,z0);

    /* x1 face +X */
    crossmod_add_dynamic_triangle(x1,y0,z0, x1,y1,z0, x1,y1,z1);
    crossmod_add_dynamic_triangle(x1,y0,z0, x1,y1,z1, x1,y0,z1);
}
"""
        surface_load_c.write_text(surface_text, encoding="utf-8")

    patch_once(
        hud,
        "void render_hud(void) {\n    s16 hudDisplayFlags;",
        "void render_hud(void) {\n"
        "    if (crossmod_bridge_active()) {\n"
        "        return;\n"
        "    }\n\n"
        "    s16 hudDisplayFlags;",
    )


    patch_once(
        gfx_d3d11,
        "    ComPtr<ID3D11DepthStencilView> depth_stencil_view;\n",
        "    ComPtr<ID3D11DepthStencilView> depth_stencil_view;\n"
        "    ComPtr<ID3D11Texture2D> depth_stencil_texture;\n"
        "    ComPtr<ID3D11ShaderResourceView> depth_shader_resource_view;\n",
    )

    patch_once(
        gfx_d3d11,
        "        d3d.backbuffer_view.Reset();\n"
        "        d3d.depth_stencil_view.Reset();\n",
        "        d3d.backbuffer_view.Reset();\n"
        "        d3d.depth_stencil_view.Reset();\n"
        "        d3d.depth_shader_resource_view.Reset();\n"
        "        d3d.depth_stencil_texture.Reset();\n",
    )

    old_depth_block = """    // Create depth buffer

    D3D11_TEXTURE2D_DESC depth_stencil_texture_desc;
    ZeroMemory(&depth_stencil_texture_desc, sizeof(D3D11_TEXTURE2D_DESC));

    depth_stencil_texture_desc.Width = desc1.Width;
    depth_stencil_texture_desc.Height = desc1.Height;
    depth_stencil_texture_desc.MipLevels = 1;
    depth_stencil_texture_desc.ArraySize = 1;
    depth_stencil_texture_desc.Format = d3d.feature_level >= D3D_FEATURE_LEVEL_10_0 ?
                                        DXGI_FORMAT_D32_FLOAT : DXGI_FORMAT_D24_UNORM_S8_UINT;
    depth_stencil_texture_desc.SampleDesc = d3d.sample_description;
    depth_stencil_texture_desc.Usage = D3D11_USAGE_DEFAULT;
    depth_stencil_texture_desc.BindFlags = D3D11_BIND_DEPTH_STENCIL;
    depth_stencil_texture_desc.CPUAccessFlags = 0;
    depth_stencil_texture_desc.MiscFlags = 0;

    ComPtr<ID3D11Texture2D> depth_stencil_texture;
    ThrowIfFailed(d3d.device->CreateTexture2D(&depth_stencil_texture_desc, nullptr, depth_stencil_texture.GetAddressOf()));
    ThrowIfFailed(d3d.device->CreateDepthStencilView(depth_stencil_texture.Get(), nullptr, d3d.depth_stencil_view.GetAddressOf()));
"""

    new_depth_block = """    // Create depth buffer. The typeless texture is both the normal SM64
    // depth-stencil target and a shader resource for the Minecraft compositor.

    const bool depth32 = d3d.feature_level >= D3D_FEATURE_LEVEL_10_0;

    D3D11_TEXTURE2D_DESC depth_stencil_texture_desc;
    ZeroMemory(&depth_stencil_texture_desc, sizeof(D3D11_TEXTURE2D_DESC));

    depth_stencil_texture_desc.Width = desc1.Width;
    depth_stencil_texture_desc.Height = desc1.Height;
    depth_stencil_texture_desc.MipLevels = 1;
    depth_stencil_texture_desc.ArraySize = 1;
    depth_stencil_texture_desc.Format = depth32 ?
                                        DXGI_FORMAT_R32_TYPELESS :
                                        DXGI_FORMAT_R24G8_TYPELESS;
    depth_stencil_texture_desc.SampleDesc = d3d.sample_description;
    depth_stencil_texture_desc.Usage = D3D11_USAGE_DEFAULT;
    depth_stencil_texture_desc.BindFlags =
        D3D11_BIND_DEPTH_STENCIL | D3D11_BIND_SHADER_RESOURCE;
    depth_stencil_texture_desc.CPUAccessFlags = 0;
    depth_stencil_texture_desc.MiscFlags = 0;

    ThrowIfFailed(d3d.device->CreateTexture2D(
        &depth_stencil_texture_desc,
        nullptr,
        d3d.depth_stencil_texture.GetAddressOf()
    ));

    D3D11_DEPTH_STENCIL_VIEW_DESC dsv_desc = {};
    dsv_desc.Format = depth32 ?
        DXGI_FORMAT_D32_FLOAT :
        DXGI_FORMAT_D24_UNORM_S8_UINT;
    dsv_desc.ViewDimension = D3D11_DSV_DIMENSION_TEXTURE2D;

    ThrowIfFailed(d3d.device->CreateDepthStencilView(
        d3d.depth_stencil_texture.Get(),
        &dsv_desc,
        d3d.depth_stencil_view.GetAddressOf()
    ));

    D3D11_SHADER_RESOURCE_VIEW_DESC depth_srv_desc = {};
    depth_srv_desc.Format = depth32 ?
        DXGI_FORMAT_R32_FLOAT :
        DXGI_FORMAT_R24_UNORM_X8_TYPELESS;
    depth_srv_desc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
    depth_srv_desc.Texture2D.MipLevels = 1;

    ThrowIfFailed(d3d.device->CreateShaderResourceView(
        d3d.depth_stencil_texture.Get(),
        &depth_srv_desc,
        d3d.depth_shader_resource_view.GetAddressOf()
    ));
"""

    patch_once(
        gfx_d3d11,
        old_depth_block,
        new_depth_block,
    )

    patch_once(
        gfx_d3d11,
        "} d3d;\n\nstatic LARGE_INTEGER",
        "} d3d;\n\n"
        '#include "mc_overlay_dx11.inc"\n\n'
        "static LARGE_INTEGER",
    )

    patch_once(
        gfx_d3d11,
        "static void gfx_d3d11_end_frame(void) {\n}\n",
        "static void gfx_d3d11_end_frame(void) {\n"
        "    mc_overlay_render();\n"
        "}\n",
    )

    makefile_text = makefile.read_text(encoding="utf-8")
    old_link = "  PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -no-pie -mwindows"
    previous_link = "  PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -no-pie -mwindows"
    previous_websocket_link = "  PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -pthread -no-pie -mwindows"
    websocket_link = "  PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -luser32 -pthread -no-pie -mwindows"

    if websocket_link not in makefile_text:
        if previous_websocket_link in makefile_text:
            makefile.write_text(
                makefile_text.replace(
                    previous_websocket_link,
                    websocket_link,
                    1,
                ),
                encoding="utf-8",
            )
        elif previous_link in makefile_text:
            makefile.write_text(
                makefile_text.replace(previous_link, websocket_link, 1),
                encoding="utf-8",
            )
        else:
            patch_once(makefile, old_link, websocket_link)


def windows_to_msys(path: pathlib.Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/{drive}{tail}"


def build_sm64_windows() -> None:
    bash = pathlib.Path(r"C:\msys64\usr\bin\bash.exe")
    mingw_gcc = pathlib.Path(r"C:\msys64\mingw64\bin\gcc.exe")

    if not bash.is_file() or not mingw_gcc.is_file():
        raise RuntimeError(
            "MSYS2 MinGW64 is not ready. Install MSYS2 and, in the "
            "MSYS2 MinGW64 terminal, run: "
            "pacman -S --needed git make python3 mingw-w64-x86_64-gcc "
            "mingw-w64-x86_64-SDL2 mingw-w64-x86_64-glew"
        )

    port_path = windows_to_msys(SM64_PORT)
    command = (
        "export PATH=/mingw64/bin:/usr/bin:$PATH; "
        f'cd "{port_path}"; '
        "make HOST_ENV=MinGW VERSION=us -j4"
    )

    run([str(bash), "-lc", command])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build-sm64",
        action="store_true",
        help="Build the patched SM64 PC host through MSYS2 MinGW64.",
    )
    args = parser.parse_args()

    try:
        verify_rom()

        if shutil.which("git") is None:
            raise RuntimeError("Git was not found in PATH.")

        VENDOR.mkdir(parents=True, exist_ok=True)

        clone_if_missing(
            "https://github.com/sm64-port/sm64-port.git",
            SM64_PORT,
        )
        clone_if_missing(
            "https://github.com/rehan-remade/universal-modder",
            UNIVERSAL_MODDER,
        )

        shutil.copy2(ROM, SM64_PORT / "baserom.us.z64")
        patch_sm64_port_toolchain()
        install_bridge()
        run([
            sys.executable,
            str(ROOT / "tools" / "verify_whole_game.py"),
            "--sm64-port",
            str(SM64_PORT),
        ])

        print()
        print("Universal Modder passthrough sources prepared.")
        print("Transport: localhost WebSocket + Local\\\\MCPassthroughFrame named shared memory.")
        print("SM64 keeps its original renderer, levels, textures, enemies and objects.")
        print("Mario is hidden when Minecraft connects and becomes an invisible interaction proxy.")

        if args.build_sm64:
            build_sm64_windows()

    except (RuntimeError, subprocess.CalledProcessError) as exception:
        print(f"ERROR: {exception}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
