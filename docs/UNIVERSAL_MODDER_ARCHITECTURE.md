# Universal Modder passthrough architecture

This branch now follows the architecture of the repository cloned by:

```
git clone https://github.com/rehan-remade/universal-modder
```

Specifically, the reference is:

`examples/minecraft-gta5-passthrough`

## What is reused directly

The SM64 setup copies the reference example's Windows WebSocket client files directly from the cloned repository:

- `examples/minecraft-gta5-passthrough/gta/src/ws.h`
- `examples/minecraft-gta5-passthrough/gta/src/ws.cpp`

No fork or alternate WebSocket implementation is substituted.

## Same data path

The crossmod now uses the same two-channel design:

1. **localhost WebSocket (127.0.0.1:25599)**
   - Minecraft is the server.
   - SM64 is the host-game client.
   - SM64 sends camera/player/progression state.
   - Minecraft sends controls and item events.

2. **named shared memory**
   - name: `Local\MCPassthroughFrame`
   - magic: `MCPT`
   - three rotating frame slots
   - odd/even sequence guard while a slot is being written
   - world RGBA8
   - world depth float32
   - transparent hand/HUD RGBA8
   - camera pose and clip-plane metadata stored with each frame

The SM64 D3D11 backend plays the role that the ReShade compositor plays in the GTA example. Because SM64-port is source-available, the compositor can live directly in the host renderer instead of requiring ReShade.

## Version adaptation

Universal Modder's current Minecraft example targets a newer Minecraft generation. This project remains Minecraft 1.21.1, so the exact renderer API calls cannot be copied byte-for-byte. The transport contract and passthrough topology are kept the same while the actual framebuffer readback uses the 1.21.1 OpenGL/Fabric APIs.

The original SM64 mission, star, save, warp and physics code remains authoritative.
