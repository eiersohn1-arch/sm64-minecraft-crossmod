#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import pathlib
import sys

EXPECTED_SHA1 = "9bef1128717f958171a4afac3ed78ee2bb4e86ce"
EXPECTED_SIZE = 8 * 1024 * 1024

def sha1(path: pathlib.Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "rom/baserom.us.z64")
    if not path.is_file():
        print(f"ERROR: ROM not found: {path}")
        return 2
    size = path.stat().st_size
    digest = sha1(path)
    print(f"ROM:   {path}")
    print(f"Size:  {size} bytes")
    print(f"SHA-1: {digest}")
    if size != EXPECTED_SIZE:
        print(f"ERROR: expected {EXPECTED_SIZE} bytes.")
        return 3
    if digest.lower() != EXPECTED_SHA1:
        print("ERROR: not the expected clean Super Mario 64 (USA) .z64 ROM.")
        return 4
    print("OK: compatible clean US SM64 ROM.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
