#!/usr/bin/env python3
"""Small SM64-specific delta on top of Universal Modder's passthrough guest.

Universal Modder remains the source of truth.  This only changes the one
camera heuristic that is GTA-specific: GTA suppresses Steve when its camera is
very close to his head.  SM64 cutscenes and Lakitu often put the camera there,
so for SM64 a requested third-person view must stay detached and render Steve.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / "generated" / "minecraft-guest"
CAMERA = GUEST / "src" / "client" / "java" / "dev" / "rehan" / "passthrough" / "client" / "mixin" / "CameraMixin.java"

if not CAMERA.is_file():
    raise SystemExit("Run tools/sync_um_reference.py first.")

text = CAMERA.read_text(encoding="utf-8")
old = "this.detached = !p.firstPerson() && !inside;"
new = "this.detached = !p.firstPerson(); // SM64: always render Steve in requested third person"
if new not in text:
    if old not in text:
        raise SystemExit("Universal Modder CameraMixin marker changed.")
    text = text.replace(old, new, 1)

CAMERA.write_text(text, encoding="utf-8")
print("Applied SM64 third-person visibility delta to Universal Modder guest.")
