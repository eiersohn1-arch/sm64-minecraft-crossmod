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
- the first compositor blends Minecraft correctly by alpha, but full SM64-vs-Minecraft depth occlusion is the next pass;
- floor collision is present, while walls/ceilings and moving surfaces still need the finer collision pass;
- Minecraft movement authority/input forwarding is not switched over yet; the first oracle keeps SM64 driving the player/camera.

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

1. depth-test Minecraft world colour against SM64's native D3D11 depth buffer;
2. stream SM64 walls, ceilings and dynamic/moving surfaces rather than only floor columns;
3. forward SM64-window keyboard/mouse into Minecraft;
4. make vanilla Minecraft locomotion authoritative and keep Mario only as an invisible SM64 interaction/progression proxy;
5. sync Minecraft-created blocks/events back into SM64 collision and gameplay.

The user's own legally obtained game files stay local.