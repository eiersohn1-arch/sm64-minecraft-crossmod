# Render and combat bridge

## Visual rule

The final scene is not reconstructed with Minecraft blocks.

SM64 renders the original game. Minecraft renders only the cross-game contribution: Steve/skin, held items, future Minecraft objects and the Minecraft HUD.

The Minecraft layer is exported with depth through the Universal Modder `MCPT` shared-memory contract and composited inside SM64's D3D11 renderer.

## State sync

SM64 sends over localhost WebSocket:

- camera position and rotation
- FOV
- authoritative player position/body yaw
- level, area, course and act
- Stars, health, coins and lives
- save/course-star flags
- mission timer
- latest bridged hit result

Minecraft sends:

- W/A/S/D and native SM64 action controls
- attack/use edge serials
- selected item
- weapon kind, reach and power
- HUD-side health/food metadata

## Combat

Minecraft attack serials are edge-triggered, so holding the mouse does not damage an SM64 object every tick.

Current adapters cover melee tools/weapons, bow/crossbow, trident and TNT. The native SM64 B action remains active so original interactions such as grabbing Big Bob-omb and Bowser still use the real mission code.

Stars, doors and ordinary scenery are excluded from generic weapon targeting.
