# Minecraft blocks on native SM64 surfaces

This milestone makes block placement/removal a real Minecraft operation while the original SM64 world remains visually and logically native.

## Placement

The visible SM64 host ray-marches from Lakitu's camera through the center crosshair and tests the real SM64 collision structures:

- floor triangles via `find_floor`;
- ceiling triangles via `find_ceil`;
- walls via `find_wall_collisions`.

The hit point and surface normal are converted from SM64's 100-units-per-block coordinate system into Minecraft coordinates and sent to the hidden Fabric guest.

Minecraft then uses `MultiPlayerGameMode.useItemOn` with the selected real Minecraft item. The target voxel is placed just outside the SM64 triangle along the surface normal.

That means placed blocks are actual Minecraft block states in the integrated Minecraft world rather than meshes faked by SM64.

## Mining and interaction

Once a Minecraft block exists in the overlay world, Minecraft's normal camera raycast sees it. Host left-click state is forwarded continuously so `startDestroyBlock`, `continueDestroyBlock` and `stopDestroyBlock` operate normally.

Entity hits and right-click item use are also routed through Minecraft's normal game-mode methods.

## Next integration layer

Placed Minecraft blocks render correctly and use Minecraft inventory/block semantics. The next engine-level step is feeding their collision boxes back into SM64's collision solver so Mario/Steve, enemies and moving objects physically collide with the blocks instead of treating them as render-only Minecraft geometry.
