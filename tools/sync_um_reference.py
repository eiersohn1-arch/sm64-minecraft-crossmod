#!/usr/bin/env python3
"""Materialise the Minecraft guest directly from Universal Modder's worked example."""
from pathlib import Path
import shutil, subprocess
ROOT=Path(__file__).resolve().parents[1]
UM=ROOT/"vendor"/"universal-modder"
SRC=UM/"examples"/"minecraft-gta5-passthrough"/"mc"
DST=ROOT/"generated"/"minecraft-guest"
if not SRC.is_dir():
    raise SystemExit("Run: python tools/bootstrap_um.py")
if DST.exists(): shutil.rmtree(DST)
DST.parent.mkdir(exist_ok=True)
shutil.copytree(SRC,DST,ignore=shutil.ignore_patterns(".gradle","build","run"))
print("Minecraft guest synced verbatim from Universal Modder:",SRC)
