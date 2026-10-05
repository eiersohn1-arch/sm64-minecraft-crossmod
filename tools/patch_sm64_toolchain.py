#!/usr/bin/env python3
"""Compatibility patch for sm64-port's bundled armips on current MinGW/GCC."""
from pathlib import Path
import argparse

def patch(sm64: Path) -> None:
    armips = sm64 / "tools" / "armips.cpp"
    if not armips.is_file():
        raise SystemExit(f"Bundled armips source missing: {armips}")

    text = armips.read_text(encoding="utf-8")

    if "#include <cstdint>\n#include <cstdio>" not in text:
        if "#include <cstdio>" not in text:
            raise SystemExit("Could not patch armips: <cstdio> marker missing.")
        text = text.replace(
            "#include <cstdio>",
            "#include <cstdint>\n#include <cstdio>",
            1,
        )

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

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--sm64", default="vendor/sm64-port")
    args=parser.parse_args()
    patch(Path(args.sm64))
