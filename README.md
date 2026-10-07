# SM64 × real Minecraft — Universal Modder passthrough

This branch uses the **real Universal Modder Minecraft passthrough**, not a handwritten Minecraft replacement.

Source of truth:

```
rehan-remade/universal-modder
└── examples/minecraft-gta5-passthrough
    ├── mc/        real Fabric Minecraft guest
    └── gta/src/   transport/reference host side
```

The project syncs that real Minecraft guest, applies only the SM64-specific control delta, then runs it behind the SM64 PC port.

## What this means

Minecraft itself owns:

- WASD movement
- gravity
- jump
- sprint
- sneak
- mouse look
- hotbar
- inventory
- item use
- block breaking
- block placement
- health/hunger
- hand/HUD/screens
- actual Minecraft player rendering

SM64 owns:

- level geometry
- stars
- doors
- warps
- missions
- enemies
- cutscenes
- progression

Mario is kept as an invisible SM64 progression proxy while Steve is the visible/player-controlled character.

## Universal Modder pieces used directly

- `HostLink`
- `FrameExporter`
- `SharedMemory`
- `PlayerSync`
- `WorldBridge`
- Minecraft client mixins
- MCPT shared-memory world/depth/HUD frame format
- `ws.cpp/ws.h` transport

The SM64-specific host code is tracked in:

```
host_adapter/
├── sm64_passthrough.h
├── sm64_passthrough.cpp
└── um_mcpt_overlay.inc
```

## Current integration

- real Win32 raw mouse input from the SM64 window
- real Minecraft key mappings
- Mario input is neutralized while Minecraft owns movement
- SM64 floor, ceiling and wall collision is streamed into Minecraft as invisible barriers
- Minecraft reports Steve's real pose back to SM64
- Mario follows Steve invisibly for stars/triggers/progression
- normal camera follows Minecraft yaw/pitch
- SM64 cutscenes temporarily own the camera/state while Minecraft follows them
- Minecraft world colour is drawn inside SM64
- Minecraft depth is converted to SM64 depth and tested against the real SM64 depth buffer
- Minecraft hand/HUD/inventory is drawn as a separate overlay
- Minecraft world/options are preserved across rebuilds
- SM64 save/config are preserved across rebuilds

## One-click Windows use

Requirements you still need once:

- Windows 10/11
- Git
- Python 3
- MSYS2 installed at `C:\msys64`
- your own clean USA `baserom.us.z64`

JDK 25 is handled automatically. If Java 25 is missing, the launcher downloads a local Temurin JDK into `.tools\jdk25`.

Put your ROM at either:

```
rom\baserom.us.z64
```

or:

```
baserom.us.z64
```

Then run:

```bat
windows-all.bat
```

That command:

1. refreshes Universal Modder;
2. syncs the real Minecraft passthrough guest;
3. applies the SM64 control delta;
4. builds the Minecraft guest;
5. builds the SM64 host;
6. starts Minecraft automatically;
7. waits for port 25599;
8. moves the Minecraft window offscreen without minimizing it;
9. starts and focuses SM64;
10. closes the guest automatically when SM64 exits.

After the first successful build you can use:

```bat
start-crossmod.bat
```

## Controls in the SM64 window

- WASD — Minecraft movement
- mouse — Minecraft look
- Space — jump
- Left Ctrl — sprint
- Left Shift — sneak
- Left click — attack / break
- Right click — use / place
- mouse wheel / 1-9 — hotbar
- E — inventory
- Q — drop
- F — swap off-hand
- F5 — first/third person

## Branch

Use:

```
universal-modder-real-minecraft
```

The older `native-minecraft-fusion` branch is the handwritten reimplementation path and is **not** the branch for this approach.
