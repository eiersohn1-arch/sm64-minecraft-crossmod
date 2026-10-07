# Native Minecraft fusion architecture

This branch follows **Universal Modder mashup Pattern 4: reimplement, then fuse**.

## One process

There is no Fabric guest, WebSocket, shared memory, localhost transport or second
Minecraft process.  The executable is the SM64 PC port plus a native C++ gameplay
runtime generated into `src/pc/native_minecraft/`.

## Authority

The native Minecraft runtime owns:
- WASD movement
- jump, sprint and sneak
- mouse yaw/pitch
- first/third person
- hotbar selection
- Minecraft-style gravity and player dimensions

SM64 still owns:
- the original world geometry
- stars, doors, warps, enemies and progression
- the original save file and level scripts

Mario remains an invisible internal proxy whose position is copied from the native
Minecraft player so existing SM64 triggers can keep working.

## Collision

The first native milestone feeds SM64 floors, walls and ceilings directly into the
Minecraft-style controller through SM64's own collision queries.  There is no
cross-process collision serialization.

## Next native systems

1. block database + raycast placement/breaking;
2. native block renderer and Steve renderer;
3. first-person arm + hotbar/inventory UI;
4. block collision inserted into SM64;
5. item/tool rules, health/hunger and crafting;
6. asset converter that reads the user's own Minecraft installation locally.

Minecraft/Mojang assets or source code are never committed.  Any retail assets must
come from the user's own installation through a local converter.
