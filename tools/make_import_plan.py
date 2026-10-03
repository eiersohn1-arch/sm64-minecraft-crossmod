#!/usr/bin/env python3
from __future__ import annotations
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROM = ROOT / "rom" / "baserom.us.z64"
LEVELS = ROOT / "data" / "levels.json"
OUT = ROOT / "generated" / "import-plan.json"

def main() -> int:
    verify = subprocess.run([sys.executable, str(ROOT / "tools" / "verify_rom.py"), str(ROM)], check=False)
    if verify.returncode:
        return verify.returncode
    data = json.loads(LEVELS.read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema": 1,
        "rom": {"path": "rom/baserom.us.z64", "verified": True},
        "status": "planning",
        "levels": [
            {**level, "geometry": "pending", "collision": "pending", "entities": "pending", "missions": "pending"}
            for level in data["levels"]
        ],
    }
    OUT.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
