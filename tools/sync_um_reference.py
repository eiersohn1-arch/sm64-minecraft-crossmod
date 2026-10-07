#!/usr/bin/env python3
"""Materialise the real Minecraft guest from Universal Modder.

The generated source is disposable, but the Minecraft run directory is not:
world/inventory/options are preserved across fresh setup/build runs.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
UM = ROOT / "vendor" / "universal-modder"
SRC = UM / "examples" / "minecraft-gta5-passthrough" / "mc"
DST = ROOT / "generated" / "minecraft-guest"
STATE = ROOT / "run" / "minecraft-guest"

if not SRC.is_dir():
    raise SystemExit("Run: python tools/bootstrap_um.py")

STATE.parent.mkdir(parents=True, exist_ok=True)

if DST.is_dir() and (DST / "run").is_dir():
    if STATE.exists():
        shutil.rmtree(STATE)
    shutil.copytree(DST / "run", STATE)

if DST.exists():
    shutil.rmtree(DST)

DST.parent.mkdir(exist_ok=True)
shutil.copytree(
    SRC,
    DST,
    ignore=shutil.ignore_patterns(".gradle", "build", "run"),
)

if STATE.is_dir():
    shutil.copytree(STATE, DST / "run")

print("Minecraft guest synced verbatim from Universal Modder:", SRC)
print("Minecraft run/world state preserved at:", STATE)
