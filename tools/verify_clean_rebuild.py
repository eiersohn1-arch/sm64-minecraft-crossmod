#!/usr/bin/env python3
"""Verify the generated clean Universal Modder SM64 passthrough architecture."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SM64 = ROOT / "vendor" / "sm64-port"
UM = ROOT / "vendor" / "universal-modder"

checks = []


def contains(path: Path, needle: str, name: str) -> None:
    text = path.read_text(encoding="utf-8")
    ok = needle in text
    checks.append((name, ok))
    if not ok:
        print(f"FAIL {name}: {needle!r} not found in {path}")


def same(a: Path, b: Path, name: str) -> None:
    ok = a.read_bytes() == b.read_bytes()
    checks.append((name, ok))
    if not ok:
        print(f"FAIL {name}: {a} differs from {b}")


pc = SM64 / "src" / "pc" / "pc_main.c"
host = SM64 / "src" / "pc" / "sm64_passthrough.cpp"
mario = SM64 / "src" / "game" / "mario.c"
gfx = SM64 / "src" / "pc" / "gfx" / "gfx_direct3d11.cpp"
overlay = SM64 / "src" / "pc" / "gfx" / "mcpt_sm64_overlay.inc"
makefile = SM64 / "Makefile"

contains(pc, "um_passthrough_start", "host lifecycle start")
contains(pc, "um_passthrough_before_frame", "pre-simulation guest pose poll")
contains(pc, "um_passthrough_after_frame", "post-simulation host publish")
contains(pc, "um_passthrough_stop", "host lifecycle stop")

contains(mario, "um_passthrough_minecraft_authority", "Minecraft locomotion authority hook")
contains(mario, "um_passthrough_apply_mario_proxy", "Mario interaction proxy sync")
contains(mario, "GRAPH_RENDER_INVISIBLE", "Mario hidden while proxying")

contains(host, '127.0.0.1', "localhost-only transport")
contains(host, 'mcpose', "guest-to-host pose feedback")
contains(host, 'minecraftAuthority ? "true" : "false"', "authority advertised to guest")
contains(host, '{\\\"t\\\":\\\"ground\\\"', "Universal Modder ground protocol")
contains(host, "find_floor", "native SM64 floor sampling")
contains(host, "sFOVState.fov + sFOVState.fovOffset", "native SM64 render FOV")
contains(host, '{\\\"t\\\":\\\"move\\\"', "vanilla Minecraft movement input forwarding")

contains(gfx, "mcpt_sm64_overlay.inc", "MCPT compositor injected into D3D11")
contains(gfx, "um_mcpt_draw", "MCPT draw at end of host frame")
contains(gfx, "depth_stencil_srv", "host depth exposed as SRV")
contains(gfx, "D3D11_BIND_SHADER_RESOURCE", "host depth shader-readable")
contains(overlay, 'Local\\\\MCPassthroughFrame', "Universal Modder MCPT mapping")
contains(overlay, "Texture2D<float> McDepth", "Minecraft depth layer")
contains(overlay, "Texture2D<float> HostDepth", "SM64 depth layer")
contains(makefile, "lws2_32", "Windows WebSocket linker dependency")

ref = UM / "examples" / "minecraft-gta5-passthrough" / "gta" / "src"
same(ref / "ws.cpp", SM64 / "src" / "pc" / "ws.cpp", "Universal Modder ws.cpp verbatim")
same(ref / "ws.h", SM64 / "src" / "pc" / "ws.h", "Universal Modder ws.h verbatim")

for name, ok in checks:
    if ok:
        print("OK  ", name)

failed = [name for name, ok in checks if not ok]
if failed:
    raise SystemExit("Clean rebuild verification failed: " + ", ".join(failed))

print("Clean Universal Modder SM64 architecture: OK")
