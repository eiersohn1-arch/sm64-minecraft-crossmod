# Native Fusion V2 architecture contract

## Pattern

Universal Modder Pattern 4: **reimplement, then fuse**.

The SM64 PC port is the host executable. Minecraft-style gameplay systems are
native C++ modules linked into the same process.

## Module boundaries

### input.cpp
Owns event-driven key/button state and raw mouse deltas. DXGI forwards `WM_INPUT`
directly into this module. No cursor recenter polling is used.

### player.cpp
Owns locomotion, acceleration, gravity, jump, sprint, sneak, player AABB,
SM64 floor/wall/ceiling collision, native voxel collision and last-safe recovery.

### world.cpp
Owns per-level/per-area native blocks, placement/break raycast, voxel collision
queries and persistent serialization to `native_minecraft_world.dat`.

### bridge.cpp
Owns authority arbitration between SM64 and the native player, Mario proxy sync,
camera sync and the public C ABI used by the C game code / D3D renderer.

### native_minecraft_render.inc
Runs inside the D3D11 backend. Native world geometry depth-tests against the
existing SM64 depth buffer. HUD and inventory are a separate overlay pass.

## Authority contract

Native Minecraft owns normal stationary/moving/airborne gameplay.

SM64 owns:
- cutscene action group
- automatic action group
- object action group
- submerged action group
- any active SM64 camera cutscene

When native authority is active, Mario's normal controller input is zeroed before
`update_mario_inputs()`. Mario is then used only as an invisible trigger/progression
proxy at the native player's pose.

When SM64 authority is active, the native player continuously mirrors Mario and
native rendering/camera override is disabled. This avoids state-machine fights.

## Build contract

`src/pc/native_minecraft` is explicitly added to `SRC_DIRS` in the generated
sm64-port Makefile. CI must compile the real object targets through `make`, not
just run isolated syntax checks.

## Asset contract

No Mojang source code or retail assets are committed.

Future texture/model support must use a local converter against the user's own
Minecraft installation. The runtime must remain usable with placeholder visuals
when those assets are absent.
