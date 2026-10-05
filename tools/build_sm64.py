#!/usr/bin/env python3
"""Build the clean Universal Modder SM64 host on Windows through MSYS2 MinGW64."""
from pathlib import Path
import os, shutil, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
SM64=ROOT/"vendor"/"sm64-port"
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

build=SM64/"build"/"us_pc"
exes=sorted(build.glob("*.exe")) if build.is_dir() else []
if not exes:
    raise SystemExit("Build finished but no SM64 .exe was found in build/us_pc.")
print("SM64 host built:",exes[0])
