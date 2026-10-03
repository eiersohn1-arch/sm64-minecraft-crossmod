# SM64 × Minecraft Crossmod

A Minecraft Java/Fabric crossmod that recreates Super Mario 64 progression inside Minecraft while keeping the normal Minecraft player, inventory, items, building and combat.

## Target

- Minecraft Java 1.21.1 + Fabric
- Minecraft player/skin, movement, inventory and items stay native
- SM64-inspired castle, levels, stars, star doors, bosses and progression are implemented as Minecraft gameplay
- Local legal SM64 US ROM is used only by developer-side extraction/conversion tools
- ROMs and extracted copyrighted assets are never committed

## Current milestone

Phase 1 establishes the Fabric mod, star progression API, data-driven level registry, ROM verification tool and importer architecture.

## Local ROM

Place your own legally obtained US ROM at:

```
rom/baserom.us.z64
```

Expected SHA-1:

```
9bef1128717f958171a4afac3ed78ee2bb4e86ce
```

The `rom/` directory and generated extracted data are gitignored.

## Build

Requires JDK 21.

```bat
gradlew.bat build
```

Run development Minecraft:

```bat
gradlew.bat runClient
```

Verify the ROM:

```bat
python tools/verify_rom.py rom/baserom.us.z64
```

## Roadmap

1. Fabric base + persistent star progression
2. Castle hub and painting portals
3. SM64 geometry/collision conversion pipeline
4. Bob-omb Battlefield vertical slice
5. Mission/star objectives
6. Enemies and bosses
7. Remaining courses, secret stages and Bowser stages
8. 120-star completion flow

This repository contains original crossmod code and converters only. It does not distribute Nintendo ROMs or extracted game assets.
