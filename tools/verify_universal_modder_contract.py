#!/usr/bin/env python3
"""Static oracle for the Universal Modder passthrough contract.

This deliberately checks architecture, not implementation trivia.  A change
must keep the same core guarantees as Universal Modder's worked
minecraft-gta5-passthrough example: localhost control IPC, MCPT shared-memory
frames, host collision fed into Minecraft, Minecraft gameplay fed back into
the host, and Minecraft-authoritative locomotion after spawn/warp alignment.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "host": ROOT / "sm64-host" / "crossmod_bridge.c",
    "guest": ROOT / "src/client/java/dev/eiersohn/sm64cross/client/bridge/GuestCommandHandler.java",
    "sync": ROOT / "src/client/java/dev/eiersohn/sm64cross/client/render/Sm64VisualSync.java",
    "frame": ROOT / "src/client/java/dev/eiersohn/sm64cross/client/render/Sm64FrameExporter.java",
    "link": ROOT / "src/client/java/dev/eiersohn/sm64cross/client/bridge/HostLink.java",
    "collision": ROOT / "src/client/java/dev/eiersohn/sm64cross/client/bridge/Sm64TerrainProxy.java",
}

texts = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}

checks = {
    "localhost websocket transport": (
        "127.0.0.1" in texts["link"] or "25599" in texts["link"]
    ),
    "MCPT shared-memory frame contract": (
        "Local\\\\MCPassthroughFrame" in texts["frame"]
        and "MAGIC = 0x5450434D" in texts["frame"]
        and "SLOTS = 3" in texts["frame"]
    ),
    "separate world/depth/overlay layers": (
        "colorPbo" in texts["frame"]
        and "depthPbo" in texts["frame"]
        and "overlayPbo" in texts["frame"]
    ),
    "asynchronous GPU readback": (
        "glFenceSync" in texts["frame"]
        and "glClientWaitSync" in texts["frame"]
    ),
    "Minecraft owns locomotion after transition": (
        "Minecraft completely owns" in texts["sync"]
        and "player.setNoGravity(false)" in texts["sync"]
    ),
    "spawn waits for host collision": (
        "Sm64TerrainProxy.isReady()" in texts["sync"]
        and "player.setNoGravity(true)" in texts["sync"]
    ),
    "host collision is streamed into Minecraft": (
        "terrain_begin" in texts["host"]
        and "terrain_box" in texts["host"]
        and "terrain_end" in texts["host"]
        and "Shapes.or" in texts["collision"]
    ),
    "Minecraft blocks collide back in SM64": (
        "crossmod_bridge_load_block_surfaces" in texts["host"]
        and "crossmod_add_dynamic_box" in texts["host"]
    ),
    "real Minecraft movement input is forwarded": (
        'case "move"' in texts["guest"]
        and "keyUp.setDown" in texts["guest"]
        and "keyJump.setDown" in texts["guest"]
        and "keySprint.setDown" in texts["guest"]
    ),
    "real Minecraft look uses vanilla sensitivity": (
        'case "look"' in texts["guest"]
        and "sensitivity().get()" in texts["guest"]
        and "client.player.turn" in texts["guest"]
    ),
    "host follows Minecraft player pose": (
        "s_guest.player_x" in texts["host"]
        and "s_guest.velocity_x" in texts["host"]
        and "GRAPH_RENDER_INVISIBLE" in texts["host"]
    ),
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("OK   " if ok else "FAIL ") + name)

if failed:
    raise SystemExit(
        "Universal Modder passthrough contract failed: " + ", ".join(failed)
    )

print("Universal Modder passthrough contract: OK")
