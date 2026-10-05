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
    # Generated/untracked adapter files are overwritten by generate_sm64_host.py.
    run("git","fetch","--depth","1","origin","master",cwd=SM64)
    run("git","reset","--hard","FETCH_HEAD",cwd=SM64)

required=[
 "skills/mashup-mods/SKILL.md",
 "examples/minecraft-gta5-passthrough/README.md",
 "examples/minecraft-gta5-passthrough/mc/src/client/java/dev/rehan/passthrough/client/HostLink.java",
 "examples/minecraft-gta5-passthrough/mc/src/client/java/dev/rehan/passthrough/client/FrameExporter.java",
 "examples/minecraft-gta5-passthrough/mc/src/client/java/dev/rehan/passthrough/client/PlayerSync.java",
 "examples/minecraft-gta5-passthrough/gta/src/ws.cpp",
 "examples/minecraft-gta5-passthrough/gta/src/ws.h",
 "examples/minecraft-gta5-passthrough/gta/src/compositor.cpp",
 "examples/minecraft-gta5-passthrough/gta/src/compositor.h",
 "examples/minecraft-gta5-passthrough/host/fakehost.py",
]
missing=[p for p in required if not (UM/p).is_file()]
if missing:
    raise SystemExit("Universal Modder reference incomplete: "+", ".join(missing))
print("Universal Modder passthrough reference ready.")
