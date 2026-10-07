# SM64 × Minecraft — native one-process fusion

This branch is the **no-second-process** rebuild.

It follows Universal Modder `mashup-mods` **Pattern 4: reimplement, then fuse**.
Minecraft-style gameplay is being implemented directly in C++ inside the SM64 PC port.

## What is gone

This branch does **not** use:

- Fabric
- Java
- Gradle
- a Minecraft guest window
- WebSocket port 25599
- shared-memory frame compositing
- the old passthrough bridge

The previous passthrough implementation remains available on the
`universal-modder-clean-rebuild` branch as a backup/reference.

## Current native core

Generated into:

```
vendor/sm64-port/src/pc/native_minecraft/
```

The first native runtime already owns:

- WASD movement
- Minecraft-style gravity
- jump with Space
- sprint with Left Ctrl
- sneak with Left Shift
- mouse yaw/pitch
- F5 first/third person state
- hotbar selection with 1-9
- SM64 floor, wall and ceiling collision
- an invisible Mario proxy that follows the native player for SM64 triggers
- the SM64 render camera driven from the native Minecraft camera

There is only **one EXE**.

## Still being built natively

The next systems are:

1. native Steve renderer
2. block storage + raycast break/place
3. rendered Minecraft blocks
4. first-person arm
5. hotbar and inventory UI
6. tools/items
7. health/hunger
8. crafting
9. block collision back into SM64 interactions
10. local asset converter for the user's own Minecraft installation

This branch never commits Mojang source code or retail assets.

## Windows

Requirements:

- Windows 10/11
- Python 3
- Git
- MSYS2 at `C:\msys64`
- MinGW64 GCC toolchain
- your own clean USA `baserom.us.z64`

Java 25 is **not required anymore**.

Put the ROM at either:

```
rom\baserom.us.z64
```

or:

```
baserom.us.z64
```

Fresh setup + build + start:

```bat
windows-all.bat
```

After a successful build:

```bat
start-crossmod.bat
```

Both launchers start the same single SM64 executable with the native runtime inside it.

## Controls

- WASD: move
- Space: jump
- Left Ctrl: sprint
- Left Shift: sneak
- Mouse: look
- F5: first/third person
- 1-9: hotbar slot

The visible Steve/block/UI layer is the next native milestone.
