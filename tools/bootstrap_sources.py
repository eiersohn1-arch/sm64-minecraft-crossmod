#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"

SOURCES = {
    "sm64-decomp": "https://github.com/n64decomp/sm64.git",
    "universal-modder": "https://github.com/rehan-remade/universal-modder.git",
}


def clone(name: str, url: str) -> None:
    target = VENDOR / name
    if (target / ".git").is_dir():
        print(f"OK: {name} already exists at {target}")
        return

    if target.exists():
        raise RuntimeError(
            f"{target} exists but is not a Git checkout. Rename/delete it and retry."
        )

    print(f"Cloning {name}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(target)],
        check=True,
    )


def main() -> int:
    if shutil.which("git") is None:
        print("ERROR: Git was not found in PATH.")
        return 2

    VENDOR.mkdir(parents=True, exist_ok=True)

    try:
        for name, url in SOURCES.items():
            clone(name, url)
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 3

    print("Source checkouts ready.")
    print("vendor/ is gitignored and will not be published with this crossmod.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
