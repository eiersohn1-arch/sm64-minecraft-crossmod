# Full Minecraft presentation inside SM64

The visible SM64 host now drives Minecraft's actual CameraType as well as the
native SM64 camera.

## F5 perspectives

F5 cycles exactly three modes:

1. first person
2. third person back
3. third person front

The host sends the current mode in the normal camera packet. Minecraft maps it
to `CameraType.FIRST_PERSON`, `THIRD_PERSON_BACK` or
`THIRD_PERSON_FRONT`.

This is important because vanilla Minecraft uses CameraType for renderer
behavior, not just for camera position.

### First person

- local Steve body is hidden by vanilla;
- vanilla `ItemInHandRenderer` runs;
- both hand and selected item keep normal swing/use animation;
- the crossmod captures the 3D Minecraft world immediately before the hand is
  drawn;
- the hand/item and HUD are therefore exported in the transparent screen-space
  overlay and can never disappear behind an SM64 wall.

### Third person

- vanilla renders the full local player model;
- skin, slim/classic arms, armor, cape/elytra and held items use the normal
  Minecraft player renderer;
- the first-person hand renderer is disabled;
- because vanilla skips the first-person hand call in third person, the
  crossmod performs its world capture at `renderLevel` TAIL instead.

This fixes a subtle old bug where third-person could stop publishing Minecraft
world frames because the exporter was attached only to the first-person hand
call.

## Minecraft-style camera geometry

Crossmod free camera now uses:

- eye/focus height: 1.62 Minecraft blocks;
- third-person distance: 4 blocks;
- FOV: 70 degrees;
- native SM64 collision clipping between player and third-person camera.

Right click no longer presses SM64's B button. It is reserved for real
Minecraft item use (eat, drink, bow, crossbow, shield, place block, interact,
etc.). Left click still reaches the native B path so original SM64 combat and
grab interactions remain compatible while Minecraft attack logic runs too.
