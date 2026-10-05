#!/usr/bin/env python3
"""Verify milestone 1 stays a clean Universal Modder passthrough."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SM64=ROOT/"vendor"/"sm64-port"
UM=ROOT/"vendor"/"universal-modder"
checks=[]

def contains(path, needle, name):
    ok=needle in path.read_text(encoding="utf-8")
    checks.append((name,ok))
    if not ok: print("FAIL",name)

def same(a,b,name):
    ok=a.read_bytes()==b.read_bytes()
    checks.append((name,ok))
    if not ok: print("FAIL",name)

pc=SM64/"src"/"pc"/"pc_main.c"
host=SM64/"src"/"pc"/"sm64_passthrough.cpp"
gfx=SM64/"src"/"pc"/"gfx"/"gfx_direct3d11.cpp"
overlay=SM64/"src"/"pc"/"gfx"/"um_mcpt_overlay.inc"
makefile=SM64/"Makefile"
ref=UM/"examples"/"minecraft-gta5-passthrough"/"gta"/"src"

same(ref/"ws.cpp",SM64/"src"/"pc"/"ws.cpp","Universal Modder ws.cpp verbatim")
same(ref/"ws.h",SM64/"src"/"pc"/"ws.h","Universal Modder ws.h verbatim")
contains(pc,"um_passthrough_start","SM64 starts UM link")
contains(pc,"um_passthrough_before_frame","SM64 pre-frame guest visibility hook")
contains(pc,"um_passthrough_frame","SM64 publishes every frame")
contains(pc,"um_passthrough_stop","SM64 stops UM link")
contains(host,'127.0.0.1',"localhost transport")
contains(host,'{\"t\":\"cam\"',"UM camera protocol")
contains(host,'{\"t\":\"ground\"',"UM ground protocol")
contains(host,'{\"t\":\"key\"',"UM input protocol")
contains(host,"gLakituState.curPos","native SM64 render camera")
contains(host,"gLakituState.curFocus","native SM64 render focus")
contains(host,"find_floor","native floor oracle")
contains(host,"GRAPH_RENDER_INVISIBLE","native Mario hidden while guest attached")
contains(gfx,'#include "um_mcpt_overlay.inc"',"MCPT compositor injected")
contains(gfx,"um_draw_mcpt","MCPT drawn in SM64 D3D11")
contains(overlay,'Local\\\\MCPassthroughFrame',"UM MCPT mapping")
contains(overlay,"World.Sample","Minecraft world layer")
contains(overlay,"Overlay.Sample","Minecraft HUD/hand layer")
contains(makefile,"lws2_32","Winsock linked")
contains(makefile,"-pthread","UM websocket thread support")

failed=[n for n,ok in checks if not ok]
for n,ok in checks:
    if ok: print("OK  ",n)
if failed:
    raise SystemExit("Clean rebuild verification failed: "+", ".join(failed))
print("Universal Modder SM64 milestone 1 contract: OK")
