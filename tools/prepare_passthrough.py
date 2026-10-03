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
        ROOT / "sm64-host" / "mc_overlay_dx11.inc",
        SM64_PORT / "src" / "pc" / "gfx" / "mc_overlay_dx11.inc",
    )

    pc_main = SM64_PORT / "src" / "pc" / "pc_main.c"
    mario = SM64_PORT / "src" / "game" / "mario.c"
    game_init = SM64_PORT / "src" / "game" / "game_init.c"
    hud = SM64_PORT / "src" / "game" / "hud.c"
    makefile = SM64_PORT / "Makefile"
    gfx_d3d11 = SM64_PORT / "src" / "pc" / "gfx" / "gfx_direct3d11.cpp"

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
        "        crossmod_bridge_after_mario_update(gMarioState);\n"
        "        gMarioState->marioObj->oInteractStatus = 0;",
    )

    patch_once(
        hud,
        '#include "print.h"\n\n/* @file hud.c',
        '#include "print.h"\n#include "pc/crossmod_bridge.h"\n\n/* @file hud.c',
    )

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

    patch_once(
        makefile,
        "  PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -no-pie -mwindows",
        "  PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -no-pie -mwindows",
    )


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
        print("Passthrough sources prepared.")
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
