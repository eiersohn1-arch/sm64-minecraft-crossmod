# SM64 × Minecraft — Native Fusion V2

This branch is the **single-process** rebuild.

It follows Universal Modder `mashup-mods` **Pattern 4: reimplement, then fuse**.
Minecraft-style systems are implemented directly in C++ inside the SM64 PC port.

There is no Fabric client, Java runtime, WebSocket, shared-memory compositor or
second Minecraft window.

## V2 architecture

The source of truth now lives in normal tracked files:

```
native_runtime/
  native_minecraft.h
  native_minecraft_internal.h
  input.cpp
  player.cpp
  world.cpp
  bridge.cpp
  native_minecraft_render.inc
```

`tools/generate_native_minecraft.py` only installs these files into a clean
`sm64-port` checkout and applies the small host hooks.

This replaces the old giant Python string-generator.

## What works in the native runtime

### Controls
- WASD movement
- Space jump
- Left Ctrl sprint
- Left Shift sneak
- raw Win32 mouse input for look
- F5 first/third person
- 1-9 hotbar
- E opens/closes the native inventory screen
- Escape closes inventory
- left click breaks native blocks
- right click places native blocks

### Player / SM64 integration
- native Minecraft-style player dimensions and gravity
- SM64 floor, wall and ceiling queries drive the controller
- 0.6-block step-up on native blocks
- last-safe-position recovery instead of falling forever into invalid collision
- Mario remains the SM64 trigger/progression proxy only while Minecraft owns normal gameplay
- controller input is neutralized so Mario and Minecraft do not move at the same time
- cutscenes, doors, automatic actions, object actions and underwater actions temporarily hand authority back to SM64
- native control resumes from Mario's resulting position afterward

### Blocks
- per-level/per-area native voxel storage
- native block raycast break/place
- native block collision
- placed blocks are saved to `native_minecraft_world.dat`
- saved blocks are restored on the next run

### Rendering
- blocky native Steve in third person
- first-person arm / held-slot block
- crosshair
- nine-slot hotbar
- survival-style HUD layout
- native inventory screen
- placed blocks rendered directly in the SM64 Direct3D 11 renderer
- native world geometry shares SM64's depth buffer
- HUD/inventory uses a separate non-depth-tested pass
- native camera and SM64 camera both use 70-degree FOV while Minecraft has authority

Retail Minecraft textures/models are intentionally not committed. A future local
asset converter can read them from the user's own legal Minecraft installation.

## Why SM64 still appears in some moments

The native runtime intentionally gives unsupported cinematic/state-machine actions
back to SM64. During star dances, doors, warps and other SM64 cutscenes, the
original Mario/camera can temporarily appear. This prevents Minecraft movement from
breaking SM64 progression.

Those actions can later be replaced one-by-one with native Steve equivalents.

## Windows requirements

- Windows 10/11
- Python 3
- Git
- MSYS2 at `C:\msys64`
- MinGW64 GCC toolchain
- your own clean USA `baserom.us.z64`

Java 25 is **not required**.

Place the ROM at either:

```
rom\baserom.us.z64
```

or:

```
baserom.us.z64
```

## Build / start

Fresh setup, build and start:

```bat
windows-all.bat
```

After a successful build:

```bat
start-crossmod.bat
```

Only one executable is launched: the SM64 PC port containing the native runtime.

## Branches

- `native-minecraft-fusion`: current V2 single-process implementation
- `universal-modder-clean-rebuild`: older two-process passthrough backup

## Still missing before this is "full Minecraft"

- real Minecraft item/tool rules
- real health/hunger simulation
- crafting
- mobs
- fluids
- block types/metadata beyond the first simple set
- full inventory interaction
- local retail-asset converter
- Steve replacements for SM64 cutscenes/actions
- more exact vanilla movement edge cases

The goal of V2 is to make those systems build on a stable single-process core
instead of adding them to another fragile bridge.
