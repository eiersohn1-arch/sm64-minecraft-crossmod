#!/usr/bin/env python3
"""Contract/regression checks for the modular Native Minecraft Fusion V2."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SM64 = ROOT / "vendor" / "sm64-port"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("FAIL: " + message)
    print("OK  ", message)


def read(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path}")
    return path.read_text(encoding="utf-8")


# The installer must be idempotent. windows-all/setup/build can legitimately
# invoke it more than once against the same checkout.
subprocess.run(
    [sys.executable, str(ROOT / "tools" / "generate_native_minecraft.py")],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [sys.executable, str(ROOT / "tools" / "generate_native_minecraft.py")],
    cwd=ROOT,
    check=True,
)

makefile = read(SM64 / "Makefile")
mario = read(SM64 / "src" / "game" / "mario.c")
camera = read(SM64 / "src" / "game" / "camera.c")
hud = read(SM64 / "src" / "game" / "hud.c")
dxgi = read(SM64 / "src" / "pc" / "gfx" / "gfx_dxgi.cpp")
d3d = read(SM64 / "src" / "pc" / "gfx" / "gfx_direct3d11.cpp")

require(
    makefile.count("src/pc/native_minecraft") == 1,
    "native source directory appears exactly once in Makefile",
)
require(
    mario.count("native_minecraft_pre_mario_action(gMarioState);") == 1,
    "Mario controller authority hook appears exactly once",
)
require(
    mario.count("native_minecraft_tick(gMarioState);") == 1,
    "native player tick appears exactly once",
)
require(
    camera.count("native_minecraft_override_camera();") == 1,
    "native camera override appears exactly once",
)
require(
    hud.count("native_minecraft_has_authority()") == 1,
    "SM64 HUD handoff appears exactly once",
)
require(
    dxgi.count("case WM_INPUT:") == 1,
    "raw mouse input hook appears exactly once",
)
require(
    dxgi.count("RegisterRawInputDevices") == 1,
    "raw mouse device registration appears exactly once",
)
require(
    dxgi.count("native_minecraft_key_event") >= 2,
    "native key down/up events are wired",
)
require(
    d3d.count('native_minecraft_render.inc') == 1,
    "native D3D11 renderer include appears exactly once",
)
require(
    d3d.count("nm_render_native_minecraft();") == 1,
    "native D3D11 render pass runs exactly once per host frame",
)

for name in (
    "native_minecraft.h",
    "native_minecraft_internal.h",
    "input.cpp",
    "player.cpp",
    "world.cpp",
    "bridge.cpp",
):
    require(
        (SM64 / "src" / "pc" / "native_minecraft" / name).is_file(),
        f"generated module exists: {name}",
    )

require(
    not (SM64 / "src" / "pc" / "ws.cpp").is_file(),
    "old passthrough websocket source is absent",
)
require(
    "MCPassthroughFrame" not in d3d,
    "old shared-memory compositor is absent",
)

player = read(SM64 / "src" / "pc" / "native_minecraft" / "player.cpp")
world = read(SM64 / "src" / "pc" / "native_minecraft" / "world.cpp")
bridge = read(SM64 / "src" / "pc" / "native_minecraft" / "bridge.cpp")
renderer = read(SM64 / "src" / "pc" / "gfx" / "native_minecraft_render.inc")

require("lastSafeX" in player, "last-safe player recovery is compiled into V2")
require("native_minecraft_world.dat" in world, "voxel world persistence is enabled")
require("ACT_GROUP_CUTSCENE" in bridge, "SM64 cutscene authority handoff is explicit")
require("native_minecraft_has_authority" in renderer, "renderer follows authority handoff")
require("d3d.depth_stencil_view" in renderer, "native world renderer shares SM64 depth buffer")

print("Native Minecraft Fusion V2 contract: OK")
