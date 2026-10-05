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

## Build

After pulling this branch:

```bat
setup-windows.bat
build-sm64.bat
```

Then start both:

```bat
start-crossmod.bat
```

For individual testing:

```bat
start-guest.bat
start-sm64.bat
start-fake-host.bat
```

If the real host build fails, send the full terminal output. The clean rebuild CI also syntax-checks the generated SM64 adapter and D3D11 compositor on Windows.

## Next order

1. prove SM64 + Minecraft world/HUD are visible together;
2. add SM64-vs-Minecraft depth occlusion;
3. add raw Minecraft mouse/WASD authority;
4. add walls, ceilings and moving SM64 collision;
5. send placed Minecraft block collision/events back into SM64;
6. add latency reprojection.

That order follows Universal Modder's rule: **cube/pose → rendering → collision → real gameplay**.
