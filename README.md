# SM64 × Minecraft Crossmod

Minecraft Java 1.21.1 + Fabric with Super Mario 64's castle/course progression rebuilt around the normal Minecraft player.

## v0.2.0 playable slice

This version boots into an automatically generated SM64 hub and contains a complete playable Bob-omb Battlefield course loop.

### Peach's Castle hub

On the first world join the mod builds the hub automatically from SM64 collision data:

- Castle Grounds
- main lobby / first floor
- upper castle
- basement
- courtyard
- connected hub warp points
- Bob-omb Battlefield painting portal
- 8-star door
- 30-star door
- 50-star door
- 70-star door
- persistent build sentinels so the huge hub is not rebuilt every launch

The generated castle currently uses Minecraft materials mapped from the SM64 collision surfaces. Exact Nintendo textures/models are not distributed in the repository.

### Bob-omb Battlefield

The course is generated from the original SM64 collision source and contains seven collectible mission stars:

1. Big Bob-omb on the Summit
   - King Bob-omb is represented by a named Minecraft Ravager boss.
2. Footrace with Koopa the Quick
   - touch the blue start marker and reach the green summit marker within 90 seconds.
3. Shoot to the Island in the Sky
   - break the mission box at the original star-box coordinate.
4. Find the 8 Red Coins
   - all eight original red-coin coordinates are used.
5. Mario Wings to the Sky
   - pass through all five original hidden-star trigger positions.
6. Behind Chain Chomp's Gate
   - break the stake at the original Chain Chomp location to open the iron-bar gate.
7. 100 Coins
   - collect 100 course coins; red coins count as two.

All mission stars have persistent IDs, so a completed star cannot be counted twice.

You remain a normal Minecraft player with your skin, inventory, armor, tools, weapons, blocks, crafting and normal Minecraft interactions.

## Requirements

- Git
- Python 3
- JDK 21
- Minecraft Java Edition
- your own clean Super Mario 64 (USA) .z64 ROM

Put your ROM at:

```text
rom/baserom.us.z64
```

Expected SHA-1:

```text
9bef1128717f958171a4afac3ed78ee2bb4e86ce
```

## Windows setup

Run:

```bat
setup-windows.bat
```

The setup performs:

1. ROM verification
2. local SM64 decomp checkout
3. local Universal Modder checkout
4. Peach's Castle generation
5. Bob-omb Battlefield generation
6. Fabric build

Local ROMs, source checkouts and generated SM64 geometry remain gitignored.

## Launch

After setup:

```bat
gradlew.bat runClient
```

Create/open a world. On the first join, Peach's Castle is generated automatically and you are moved to the SM64 starting area.

The castle contains a blue Bob-omb painting. Walk into it to enter Bob-omb Battlefield.

A purple pad near the Bob-omb start returns you to the castle.

## Useful commands

```text
/sm64
/sm64 stars
/sm64 castle
/sm64 bob
/sm64 buildstatus
/sm64 level info bob_omb_battlefield
```

`/sm64 castle` is a fallback teleport to the castle lobby.

`/sm64 bob` is a fallback teleport directly into Bob-omb Battlefield.

## Verified importer numbers

The automated GitHub validation currently reads from upstream SM64 decomp data and verifies approximately:

- Bob-omb Battlefield: 570 collision vertices
- Bob-omb Battlefield: 1060 collision triangles
- Bob-omb Battlefield: 49,982 generated terrain blocks
- Bob-omb Battlefield: 7 mission objectives
- Bob-omb Battlefield: 8 original red coins
- Bob-omb Battlefield: 94 normal coin markers plus red-coin value, enough for the 100-coin star
- Peach's Castle hub: 5 playable areas
- Peach's Castle hub: about 108,835 generated blocks

## Important scope

The hub/course geometry and mission coordinates come from the user's local/public decomp workflow. The repository contains original crossmod code and converters, not Nintendo ROMs or extracted retail assets.

The current visuals are Minecraft-material recreations of the SM64 collision geometry. Exact visual-mesh conversion, original-looking textures, more faithful enemy AI, every remaining SM64 course, secret stages and Bowser stages are later milestones.
