# SM64 × Minecraft — Universal Modder clean rebuild

This branch intentionally contains **no code from the previous crossmod implementation**.

Source of truth: `rehan-remade/universal-modder`, skill `mashup-mods`, Pattern 2 (passthrough), worked example `examples/minecraft-gta5-passthrough`.

## Current milestone

The clean rebuild now has a real end-to-end path:

```
SM64 PC port (DX11)
  -> localhost WebSocket camera/player pose
Minecraft 26.3 + Fabric (Universal Modder guest)
  -> Local\MCPassthroughFrame
SM64 DX11 compositor
  -> Minecraft world + hand/HUD over the SM64 backbuffer
```

SM64 also samples its native `find_floor()` collision around Mario and sends it through Universal Modder's existing
`{"t":"ground","c":[...]}` protocol. The guest turns those columns into invisible barrier collision.

This is still a milestone build:
- Minecraft world colour is depth-tested against SM64's native D3D11 depth buffer; hand/HUD/screens stay on top;
- Minecraft now owns normal locomotion: WASD, jump, sneak, sprint, vanilla gravity and velocity;
- Minecraft sends `mcpose` back to SM64 and Mario becomes an invisible interaction/progression proxy;
- SM64 automatically takes authority back for cutscene/automatic/object action groups so native scripted sequences can continue;
- left/right click, hotbar 1-9, E, Q, F and Escape are forwarded from the focused SM64 window;
- the visible camera is still SM64-authoritative for this milestone; Minecraft-style mouse look/F5 comes next;
- floor collision is present, while walls/ceilings and moving surfaces still need the finer collision pass.

## Architecture

Two real runtimes run at once:

- **SM64 host**: original SM64 PC port, original levels/progression/rendering.
- **Minecraft guest**: the current Universal Modder Minecraft passthrough client.
- **Control IPC**: localhost WebSocket from Universal Modder.
- **Frames**: Minecraft world colour + depth + separate hand/HUD overlay through MCPT shared memory.
- **Collision back-channel**: native SM64 floor collision becomes invisible Minecraft barriers.
- **Renderer**: the MCPT frame is consumed directly by SM64's native Direct3D 11 renderer.

No old `crossmod_bridge.c`, custom HUD, movement authority shim, terrain proxy or previous compositor is reused.

## Windows requirements

- Windows 10/11
- **JDK 25**
- Python 3
- Git
- MSYS2 in `C:\msys64`
- MinGW64 build packages for the SM64 PC port
- your own clean USA `baserom.us.z64`

Put the ROM at either:

```
rom\baserom.us.z64
```

or:

```
baserom.us.z64
```

The ROM is ignored by Git and is never committed.

## Build and run

From the repository root:

```bat
setup-windows.bat
build-sm64.bat
start-crossmod.bat
```

What each file does:

- `setup-windows.bat` refreshes Universal Modder, clones a clean `sm64-port`, copies the current Universal Modder Minecraft guest, and generates the clean SM64 host/compositor adapter.
- `build-sm64.bat` copies your local ROM into the temporary vendor checkout and builds the DX11 SM64 host with MSYS2/MinGW64.
- `start-crossmod.bat` starts the Minecraft guest and then the real SM64 host. Both sides reconnect automatically if one starts more slowly.

For individual testing:

```bat
start-guest.bat
start-sm64.bat
start-fake-host.bat
```

## Next milestones

1. add Minecraft-style raw mouse look and F5 first/third-person camera authority;
2. stream SM64 walls, ceilings and dynamic/moving surfaces rather than only floor columns;
3. sync Minecraft-created block collision/events back into SM64;
4. add frame reprojection/latency compensation on top of the working depth compositor;
5. switch the SM64 guest profile from the reference creative setup toward the requested survival hearts/hunger behavior without breaking the passthrough oracle.

The user's own legally obtained game files stay local.