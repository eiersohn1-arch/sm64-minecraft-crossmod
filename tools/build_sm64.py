#!/usr/bin/env python3
"""Build the clean Universal Modder SM64 host on Windows through MSYS2 MinGW64."""
from pathlib import Path
import os, shutil, subprocess, sys
from patch_sm64_toolchain import patch as patch_sm64_toolchain

ROOT=Path(__file__).resolve().parents[1]
SM64=ROOT/"vendor"/"sm64-port"
RUN_STATE=ROOT/"run"/"sm64"
STATE_FILES=("sm64_save_file.bin","sm64config.txt")
ROM_CANDIDATES=[
    ROOT/"rom"/"baserom.us.z64",
    ROOT/"baserom.us.z64",
]
rom=next((p for p in ROM_CANDIDATES if p.is_file()),None)
if rom is None:
    raise SystemExit(
        "SM64 USA ROM missing. Put your own baserom.us.z64 in the project root "
        "or in rom\\baserom.us.z64, then run this again."
    )
if not (SM64/"Makefile").is_file():
    raise SystemExit("Run setup-windows.bat first.")


def preserve_run_state() -> None:
    RUN_STATE.mkdir(parents=True, exist_ok=True)
    build_dir = SM64 / "build" / "us_pc"
    if build_dir.is_dir():
        for name in STATE_FILES:
            src = build_dir / name
            if src.is_file():
                shutil.copy2(src, RUN_STATE / name)


def restore_run_state() -> None:
    build_dir = SM64 / "build" / "us_pc"
    if not build_dir.is_dir():
        return
    for name in STATE_FILES:
        src = RUN_STATE / name
        if src.is_file():
            shutil.copy2(src, build_dir / name)


def prepare_clean_vendor() -> None:
    """Rebuild the generated host from a pristine sm64-port checkout."""
    if not (SM64 / ".git").is_dir():
        raise SystemExit("vendor/sm64-port is not a Git checkout. Run setup-windows.bat first.")

    preserve_run_state()

    # vendor/sm64-port is disposable generated state. Resetting + cleaning here
    # prevents old untracked crossmod_bridge.c/crossmod_ws_api.* files from
    # silently being picked up by sm64-port's wildcard Makefile.
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=SM64, check=True)
    subprocess.run(["git", "clean", "-fdx"], cwd=SM64, check=True)

    legacy = [
        SM64 / "src" / "pc" / "crossmod_bridge.c",
        SM64 / "src" / "pc" / "crossmod_bridge.h",
        SM64 / "src" / "pc" / "crossmod_ws_api.cpp",
        SM64 / "src" / "pc" / "crossmod_ws_api.h",
        SM64 / "src" / "pc" / "gfx" / "mc_overlay_dx11.inc",
    ]
    leftovers = [str(p.relative_to(SM64)) for p in legacy if p.exists()]
    if leftovers:
        raise SystemExit("Legacy crossmod files survived cleanup: " + ", ".join(leftovers))

    # Always regenerate the current clean host after git pull so users never
    # build an older generated adapter by accident.
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "generate_sm64_host.py")],
        cwd=ROOT,
        check=True,
    )


prepare_clean_vendor()
patch_sm64_toolchain(SM64)

shutil.copy2(rom,SM64/"baserom.us.z64")

bash_candidates=[
    Path(os.environ.get("MSYS2_ROOT",r"C:\msys64"))/"usr"/"bin"/"bash.exe",
    Path(r"C:\msys64\usr\bin\bash.exe"),
    Path(r"C:\tools\msys64\usr\bin\bash.exe"),
]
bash=next((p for p in bash_candidates if p.is_file()),None)
if bash is None:
    raise SystemExit(
        "MSYS2 was not found. Install MSYS2 to C:\\msys64 and install the "
        "MinGW64 build packages, then run setup-windows.bat again."
    )

def msys_path(path: Path)->str:
    s=str(path.resolve()).replace("\\","/")
    if len(s)>=2 and s[1]==":":
        return "/"+s[0].lower()+s[2:]
    return s

cmd=(
    "export PATH=/mingw64/bin:/usr/bin:$PATH; "
    f'cd "{msys_path(SM64)}"; '
    "make VERSION=us -j4"
)
print("+",bash,"-lc",cmd)
subprocess.run([str(bash),"-lc",cmd],check=True)

restore_run_state()

build=SM64/"build"/"us_pc"
exes=sorted(build.glob("*.exe")) if build.is_dir() else []
if not exes:
    raise SystemExit("Build finished but no SM64 .exe was found in build/us_pc.")
print("SM64 host built:",exes[0])
