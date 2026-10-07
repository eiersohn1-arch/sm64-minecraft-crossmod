#!/usr/bin/env python3
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/"vendor"
UM=VENDOR/"universal-modder"
SM64=VENDOR/"sm64-port"

def run(*args,cwd=None):
    print("+"," ".join(map(str,args)))
    subprocess.run(args,cwd=cwd,check=True)

VENDOR.mkdir(exist_ok=True)
if not (UM/".git").is_dir():
    run("git","clone","--depth","1","https://github.com/rehan-remade/universal-modder",UM)
else:
    run("git","fetch","--depth","1","origin","main",cwd=UM)
    run("git","reset","--hard","FETCH_HEAD",cwd=UM)

if not (SM64/".git").is_dir():
    run("git","clone","--depth","1","https://github.com/sm64-port/sm64-port.git",SM64)
else:
    # Every generated host must start from clean upstream tracked sources.
    # Generated/untracked native fusion files are overwritten by generate_native_minecraft.py.
    run("git","fetch","--depth","1","origin","master",cwd=SM64)
    run("git","reset","--hard","FETCH_HEAD",cwd=SM64)

required=[
 "skills/mashup-mods/SKILL.md",
]
missing=[p for p in required if not (UM/p).is_file()]
if missing:
    raise SystemExit("Universal Modder reference incomplete: "+", ".join(missing))
print("Universal Modder Pattern 4 reference ready.")
