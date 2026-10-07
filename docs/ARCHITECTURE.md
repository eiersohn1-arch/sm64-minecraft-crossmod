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

## Collision and editable world

The bridge is now bidirectional, not just host ground -> Minecraft.

### SM64 -> Minecraft

Each SM64 save/level/area is assigned a deterministic hidden Minecraft coordinate zone. The host streams nearby floors, ceilings and walls into that zone as `passthrough:sm64_surface`, a technical Minecraft block with normal targeting/collision and finite mining strength. It has no BlockItem, so the player cannot obtain fake Mario terrain as an inventory item.

When Steve mines one of those cells, the guest writes a persistent tombstone under `sm64-surface-breaks/<context>.txt`. Later terrain packets skip that cell, so mining is stable across restarts and level revisits.

### Minecraft -> SM64

Universal Modder's existing block-change stream is consumed by the SM64 host. Nearby real Minecraft blocks are cached and rebuilt each frame as native SM64 dynamic collision boxes after moving-platform collision has loaded. Existing builds are re-synced after a warp with `blocksync`.

That means placement is not just visual composition: Minecraft owns the block, and SM64 receives physical collision for it too.

The host samples nearby:

- `find_floor()`
- `find_ceil()`
- `find_wall_collisions()`

Those samples are sent through Universal Modder's existing `ground` protocol and become invisible Minecraft barrier blocks via the unchanged `WorldBridge.solid()`.

Minecraft-placed blocks stay real Minecraft blocks; Universal Modder's server-side block tracking continues to report their changes.

## Original SM64 interactions

Minecraft still owns movement physics, but the host maps Minecraft controls into semantic SM64 buttons on the invisible Mario proxy:

- Space -> A
- left/right click -> B
- Shift -> Z

Analog stick input remains zero. This lets native SM64 interaction/action code continue to process doors, switches, breakables and other mission mechanics without re-enabling Mario locomotion.

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
