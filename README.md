# SM64 × Minecraft Crossmod

A Minecraft Java/Fabric crossmod that rebuilds Super Mario 64 progression around the normal Minecraft player.

## Target

- Minecraft Java 1.21.1 + Fabric
- You remain your normal Minecraft character/skin
- Vanilla inventory, tools, weapons, blocks, crafting and building stay enabled
- SM64 castle/course/star progression is added as Minecraft gameplay
- Local user-owned SM64 data is converted on the user's machine
- ROMs and extracted copyrighted assets are never committed

## Current playable prototype

The project already contains:

- persistent 0–120 Power Star progress
- unique mission IDs so the same mission star does not count twice
- a real SM64 collision parser
- Bob-omb Battlefield collision → Minecraft block voxelization
- original Bob-omb Battlefield mission/object coordinate parsing
- the original 8 red-coin positions
- a playable 8 Red Coins star
- the original static Star 6 position
- incremental course construction so Minecraft is not frozen by one huge placement tick

The other missions, enemies, visuals, castle, painting portals and remaining courses are still being implemented.

## Local requirements

- Git
- Python 3
- JDK 21
- Minecraft Java Edition
- your own clean Super Mario 64 (USA) .z64 ROM

Put the ROM here:

```text
rom/baserom.us.z64
```

Expected SHA-1:

```text
9bef1128717f958171a4afac3ed78ee2bb4e86ce
```

## One-command setup on Windows

Open the project folder and run:

```bat
setup-windows.bat
```

It will:

1. verify your local ROM
2. clone the public SM64 decomp locally into gitignored `vendor/`
3. clone Universal Modder locally into gitignored `vendor/`
4. generate the Bob-omb Battlefield Minecraft block plan
5. build the Fabric mod

Then launch the dev client:

```bat
gradlew.bat runClient
```

Create a cheats-enabled Creative world. Stand in a large empty area and run:

```text
/sm64 build bob_omb_battlefield
```

Useful commands:

```text
/sm64
/sm64 stars
/sm64 buildstatus
/sm64 level info bob_omb_battlefield
```

## What to expect in the current prototype

The course terrain is generated from the real SM64 collision mesh, converted to Minecraft blocks. It is intentionally a first-pass block representation, not the final textured visual conversion.

Red concrete blocks mark the eight original red-coin coordinates. Walk through all eight and a gold-block Power Star marker appears at the original SM64 red-coin-star position. Walk into the star marker to collect it.

A second gold star marker corresponds to the original static Star 6 position.

## Universal Modder

Universal Modder is used as an analysis/orchestration aid for mashup design, Minecraft modding and retro-decomp workflows. It is not treated as a one-click converter.

## Safety of your game files

`rom/`, `vendor/`, `generated/`, `extracted/` and the Minecraft `run/` development directory are gitignored. The repository publishes crossmod code and converters, not your ROM or locally extracted Nintendo assets.
