# SM64 × Minecraft — Universal Modder clean rebuild

This branch is a clean rebuild around **Universal Modder `mashup-mods` Pattern 2 (passthrough)**. None of the old crossmod bridge/HUD/terrain code is reused.

## Current milestone: first real SM64 host

The path is now:

```
real SM64 PC port (Direct3D 11)
       |
       |  Universal Modder localhost WebSocket
       v
real Minecraft 26.3 + Fabric guest
       |
       |  Local\MCPassthroughFrame
       v
SM64 D3D11 backbuffer
```

The Minecraft guest is copied **verbatim** from Universal Modder's
`examples/minecraft-gta5-passthrough/mc`.

The SM64 adapter:
- uses Universal Modder's `ws.cpp/ws.h` verbatim;
- sends the real SM64 camera and Mario position with the same `cam` protocol;
- samples native SM64 `find_floor()` collision and sends `ground` columns;
- forwards left/right click, E, Q, F and hotbar 1-9 using the existing UM input messages;
- reads the UM `MCPT` shared-memory ring;
- composites Minecraft world colour plus the separate hand/HUD/GUI layer into SM64's D3D11 frame.

This is deliberately the **small vertical slice Universal Modder recommends**. Minecraft follows the SM64 host in this milestone. Depth occlusion, Minecraft-authoritative WASD/mouse movement, walls/ceilings and block collision back into SM64 come after this slice is proven on the real PC.

## Requirements

- Windows 10/11
- JDK 25
- Python 3
- Git
- MSYS2 installed at `C:\msys64`
- MinGW64 GCC toolchain
- your own clean USA `baserom.us.z64`

Put the ROM in either:

```
rom\baserom.us.z64
```

or the repository root as `baserom.us.z64`.

## Windows: one-click flow

After pulling this branch, the recommended Windows path is now simply:

```bat
windows-all.bat
```

That one launcher runs the unified `windows-crossmod.ps1` controller. It:

1. checks Git, Python, **JDK 25**, MSYS2 and the ROM;
2. installs/validates the required MSYS2 MinGW packages;
3. refreshes Universal Modder and a clean `sm64-port`;
4. recreates the Minecraft guest directly from Universal Modder;
5. removes all stale/generated legacy crossmod files;
6. patches old `sm64-port` build tools for current MinGW;
7. rebuilds the generated SM64 host from a pristine checkout;
8. launches Minecraft;
9. waits for the Universal Modder WebSocket on `127.0.0.1:25599`;
10. only then starts the SM64 host.

Your own clean USA ROM must be at either:

```
rom\baserom.us.z64
```

or:

```
baserom.us.z64
```

Useful individual launchers still exist, but they all route through the same PowerShell controller:

```bat
windows-doctor.bat
setup-windows.bat
build-sm64.bat
start-guest.bat
start-sm64.bat
start-crossmod.bat
```

For normal use, prefer `windows-all.bat` for a fresh build or `start-crossmod.bat` after a successful build.

## Minecraft controls in the SM64 window

When the crossmod is connected, the **SM64 window is the active game window**, but these inputs are forwarded into the real Minecraft player:

- `W A S D`: vanilla Minecraft movement
- `Space`: jump
- `Left Shift`: sneak
- `Left Ctrl`: sprint
- mouse: Minecraft look
- left click: attack / break
- right click: use / place
- `1-9`: hotbar
- `E`: inventory
- `Q`: drop
- `F`: swap off-hand
- `F5`: first/third person

Minecraft now owns normal locomotion and gravity.  SM64's Mario is kept invisible and is snapped to Steve's reported Minecraft pose so SM64 stars, triggers, doors and progression can continue to use Mario as an interaction proxy.

## Next order

1. prove SM64 + Minecraft world/HUD are visible together;
2. add SM64-vs-Minecraft depth occlusion;
3. add raw Minecraft mouse/WASD authority;
4. add walls, ceilings and moving SM64 collision;
5. send placed Minecraft block collision/events back into SM64;
6. add latency reprojection.

That order follows Universal Modder's rule: **cube/pose → rendering → collision → real gameplay**.
