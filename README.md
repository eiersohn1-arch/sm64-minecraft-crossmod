# SM64 × Minecraft — Universal Modder clean rebuild

This branch intentionally contains **no code from the previous crossmod implementation**.

Source of truth: `rehan-remade/universal-modder`, skill `mashup-mods`, Pattern 2 (passthrough), worked example `examples/minecraft-gta5-passthrough`.

## Architecture

Two real runtimes run at once:

- **SM64 host**: original SM64 PC port, original levels/progression/rendering.
- **Minecraft guest**: real Minecraft + Fabric simulation, vanilla movement/input/items/HUD.
- **Control IPC**: localhost WebSocket, matching Universal Modder's worked example.
- **Frames**: Minecraft world colour + depth + separate hand/HUD overlay through MCPT shared memory.
- **Collision back-channel**: nearby SM64 collision is converted to invisible Minecraft collision.
- **Effects back-channel**: Minecraft block/gameplay events are sent to the SM64 host.

No old `crossmod_bridge.c`, custom HUD, movement authority shim, terrain proxy or previous compositor is reused.

## Build order

1. Bootstrap exact Universal Modder reference and SM64 source.
2. Bring up Minecraft guest + localhost control link unchanged in topology.
3. Bring up a fake SM64 host oracle before touching the real game.
4. Export Minecraft colour/depth/overlay using the MCPT contract.
5. Add the SM64 host adapter and depth compositor.
6. Feed SM64 collision into Minecraft.
7. Add Minecraft block/action effects back into SM64.
8. Only after the cube/camera/collision oracle is green, enable full gameplay.

The user's own legally obtained SM64 ROM is supplied locally and is never committed.
