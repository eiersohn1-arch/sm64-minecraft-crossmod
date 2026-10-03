# Correct target: SM64 runtime + Minecraft player

The block-recreation prototype is archived on the `legacy-block-prototype` branch.

The main branch now targets a passthrough mashup.

## What remains Super Mario 64

The SM64 PC port is the world/runtime authority for:

- Peach's Castle
- every SM64 course and secret stage
- original level geometry
- original textures extracted locally from the user's ROM
- skyboxes
- paintings
- doors
- Power Stars
- Red Coins
- Goombas, Bob-ombs, Boos, Chain Chomp and other SM64 actors
- bosses
- moving platforms
- warps
- music and sound
- level scripts and progression

The repository never stores the user's ROM or the extracted retail assets.

## What comes from Minecraft

Minecraft is the player/inventory authority for:

- Steve/Alex or the user's skin
- Minecraft movement
- hotbar
- inventory
- armor
- hunger and Minecraft health
- held items
- tools
- swords
- bows/projectiles
- food
- potions
- TNT
- player-placed Minecraft blocks

## Hidden proxy

SM64 still needs a Mario object because its cameras, enemies, Stars, doors and triggers expect Mario.

When the localhost bridge is connected:

1. the actual Mario model is hidden;
2. Minecraft sends Steve's position and rotation to SM64 each tick;
3. the invisible Mario proxy follows Steve;
4. SM64 interactions run against that invisible proxy;
5. SM64 sends level/progression/event state back to Minecraft.

This allows SM64's real gameplay runtime to keep working while the visible player is Steve.

## Rendering/compositing milestones

### M1 — bridge
Minecraft player state -> hidden SM64 Mario proxy.

### M2 — collision
SM64 collision -> invisible Minecraft collision proxy. It exists only for Minecraft physics and is never the visual level.

### M3 — composition
SM64 color/depth is shared with Minecraft. Minecraft renders only Steve, Minecraft items/blocks and HUD over the SM64 frame with depth testing.

### M4 — item effects
Minecraft attack/use/projectile/explosion events are mapped into the SM64 runtime.

Examples:

- sword -> damage SM64 enemy hit by Steve's ray/weapon reach
- bow -> Minecraft projectile rendered in the composite and hit-tested against SM64
- TNT -> Minecraft explosion plus mapped SM64 enemy/object damage
- food/potions -> normal Minecraft player effects
- blocks -> player-created Minecraft geometry rendered on top of SM64 and added to Minecraft collision

## Important

The old colored/stone/grass conversion is not the target visual renderer anymore. Collision conversion may still be reused internally as an invisible physics proxy.
