# 3D render and combat bridge

## Visual rule

The final scene is not rebuilt from Minecraft blocks.

The base frame comes from the native Super Mario 64 renderer, so the following remain genuine SM64 geometry/materials/objects:

- Peach's Castle and castle grounds
- every course and secret stage
- skyboxes
- paintings and doors
- enemies and bosses
- Power Stars and coins
- moving platforms and level props
- SM64 lighting/fog/render layers

Minecraft contributes only cross-game content:

- Steve/Alex/custom player skin
- held Minecraft item
- Minecraft hotbar/inventory/health/hunger
- player-placed Minecraft blocks
- Minecraft projectiles/effects that are explicitly bridged

## Current render synchronization

The localhost state packet now sends:

- SM64 proxy-player position
- SM64 camera position
- SM64 camera focus
- SM64 camera mode
- level and area
- Star/health state
- latest Minecraft melee hit result

This is the camera contract required by the compositor. Minecraft can use the SM64 camera pose rather than inventing a separate Minecraft camera, which keeps Steve visually locked into the original SM64 3D scene.

## Melee combat

Minecraft sends a monotonically increasing attack serial only when a new left-click attack starts. The host therefore performs one SM64 hit per Minecraft swing instead of damaging enemies every tick while the mouse is held.

Current melee profiles include swords, axes, mace, trident, tools and empty hand. Bow/crossbow are reserved for the projectile bridge.

Targeting uses distance, Steve's facing direction, an attack cone and the SM64 object's interaction type. Stars, doors and normal scenery are not selected as melee targets.

When hit, the object receives SM64's normal attacked/interacted flags. Existing SM64 behavior remains responsible for the actual reaction.

## Next compositor step

The next rendering layer shares the SM64 color and depth targets with Minecraft, then draws Steve/items against that depth. This gives correct occlusion: Steve can be hidden behind an SM64 wall, while Minecraft items/blocks can still appear inside the SM64 scene.

The old block conversion remains only on the archived legacy-block-prototype branch.
