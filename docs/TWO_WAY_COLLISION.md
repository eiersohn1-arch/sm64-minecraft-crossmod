# SM64 -> Minecraft local collision shell

Minecraft entities need collision even though the visible course is rendered by
SM64 rather than Minecraft blocks.

The host samples native static SM64 collision around the player and maintains
invisible Minecraft barrier cells for:

- floor height;
- nearby vertical walls at several mob-height samples;
- low ceilings.

These proxy cells are server-side Minecraft collision, so mobs, arrows,
tridents and dropped items can interact with the local course shape.

Proxy cells are tracked separately from user-created blocks. Minecraft raycasts
used by the crossmod ignore only tracked proxy cells; a player-created real
barrier block remains a normal Minecraft block. The block-collision publisher
also excludes only proxy cells, preventing a feedback loop back into SM64.

This remains a local voxel approximation for Minecraft entity physics. Visible
geometry, exact player physics and mission collision stay native SM64 triangles.
