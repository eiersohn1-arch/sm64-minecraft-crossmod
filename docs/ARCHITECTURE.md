# Architecture — real Universal Modder passthrough

## Pattern

Universal Modder `mashup-mods` Pattern 2: passthrough.

Two real runtimes are active:

```
SM64 PC port
   |
   | camera / input / collision
   v
Universal Modder HostLink (127.0.0.1:25599)
   |
   v
real Minecraft + Fabric
   |
   | world RGBA + depth + hand/HUD overlay
   v
Local\MCPassthroughFrame
   |
   v
SM64 Direct3D 11 compositor
```

## Authority

### Minecraft owns normal gameplay

When the Minecraft pose stream is valid and SM64 is not in an unsupported cinematic/action state:

- SM64 controller input is zeroed;
- WASD/mouse/buttons from the SM64 window are forwarded to Minecraft;
- Minecraft performs movement and item/block logic;
- Minecraft reports player position/velocity/yaw/pitch;
- invisible Mario is moved to that pose.

### SM64 owns progression/cinematics

SM64 retains:

- stars/triggers
- doors/warps
- mission logic
- native enemies
- cutscenes
- automatic/object/submerged actions

During those states Minecraft switches from drive mode to host-follow mode, so its player/camera follows the SM64 state instead of fighting it.

## Collision

The host samples nearby:

- `find_floor()`
- `find_ceil()`
- `find_wall_collisions()`

Those samples are sent through Universal Modder's existing `ground` protocol and become invisible Minecraft barrier blocks via the unchanged `WorldBridge.solid()`.

Minecraft-placed blocks stay real Minecraft blocks; Universal Modder's server-side block tracking continues to report their changes.

## Input

The SM64 DXGI window registers Win32 raw mouse input.

The host forwards:

- event-driven key/button state
- raw mouse deltas
- wheel
- hotbar selections

Movement/look are applied to the real Minecraft client's mappings/player, not reimplemented in SM64.

## Rendering

The unchanged Universal Modder `FrameExporter` writes:

- world RGBA
- reversed-Z Minecraft depth
- hand/HUD/screens RGBA

to `Local\MCPassthroughFrame`.

SM64's D3D11 adapter:

1. uploads the newest MCPT world/depth/overlay slot;
2. linearizes Minecraft depth using Universal Modder's formula;
3. converts that distance into SM64's 1..300 block-equivalent depth range;
4. outputs it as `SV_Depth`;
5. lets the existing SM64 depth buffer perform occlusion;
6. draws the hand/HUD/inventory overlay afterward with depth disabled.

## Source rule

Universal Modder remains the source of truth for the Minecraft guest and websocket transport.

SM64-specific changes are limited to:

- guest control/drive-mode delta
- host adapter
- host hooks
- launcher/build automation

Do not replace this branch with a handwritten Minecraft runtime.
