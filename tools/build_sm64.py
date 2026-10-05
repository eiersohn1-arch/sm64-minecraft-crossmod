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


def patch_old_sm64_build_tools() -> None:
    """Make sm64-port's bundled armips build on current MinGW/GCC."""
    armips = SM64 / "tools" / "armips.cpp"
    if not armips.is_file():
        raise SystemExit(f"Bundled armips source missing: {armips}")

    text = armips.read_text(encoding="utf-8")

    # Modern MinGW can encounter SymbolTable's int64_t declarations before a
    # header has actually defined int64_t.  That produces the misleading
    # declaration/definition mismatch shown by GCC while building armips.
    if "#include <cstdint>\n#include <cstdio>" not in text:
        marker = "#include <cstdio>"
        if marker not in text:
            raise SystemExit("Could not patch armips: <cstdio> marker missing.")
        text = text.replace(
            marker,
            "#include <cstdint>\n#include <cstdio>",
            1,
        )

    # armips stores paths as std::wstring.  Current MinGW may resolve the
    # generic Win32 macros to the ANSI A functions unless UNICODE is globally
    # defined.  Call the wide variants explicitly.
    text = text.replace(
        "GetFileAttributesEx(fileName.c_str(),GetFileExInfoStandard,&attr)",
        "GetFileAttributesExW(fileName.c_str(),GetFileExInfoStandard,&attr)",
    )
    text = text.replace(
        "GetFileAttributes(strFilename.c_str())",
        "GetFileAttributesW(strFilename.c_str())",
    )

    armips.write_text(text, encoding="utf-8")
    print("Patched bundled armips for current MinGW/GCC.")

patch_old_sm64_build_tools()

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
