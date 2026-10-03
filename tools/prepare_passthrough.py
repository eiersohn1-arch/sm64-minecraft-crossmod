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

    pc_main = SM64_PORT / "src" / "pc" / "pc_main.c"
    mario = SM64_PORT / "src" / "game" / "mario.c"
    hud = SM64_PORT / "src" / "game" / "hud.c"
    makefile = SM64_PORT / "Makefile"

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

    original = (
        "    if (gMarioState->action) {\n"
        "        gMarioState->marioObj->header.gfx.node.flags &= ~GRAPH_RENDER_INVISIBLE;\n"
        "        mario_reset_bodystate(gMarioState);"
    )

    replacement = (
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

    patch_once(mario, original, replacement)

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
        "make VERSION=us -j4"
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
            "https://github.com/rehan-remade/universal-modder.git",
            UNIVERSAL_MODDER,
        )

        shutil.copy2(ROM, SM64_PORT / "baserom.us.z64")
        patch_sm64_port_toolchain()
        install_bridge()

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
