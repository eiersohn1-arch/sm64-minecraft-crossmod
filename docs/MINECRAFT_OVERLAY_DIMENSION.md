# Minecraft overlay dimension

The hidden Minecraft client/server now uses a real empty dimension:

`sm64cross:sm64_overlay`

This is required for genuine Minecraft gameplay. The previous render-only origin at Y=10000 was outside vanilla build height, so real block placement could not be a complete Minecraft operation.

The new dimension is a flat generator with no terrain layers. Its coordinate origin is shifted upward by 128 blocks:

`Minecraft Y = SM64 Y / 100 + 128`

The original SM64 level range therefore fits inside normal Minecraft build height while vanilla terrain stays absent.

In singleplayer the common Fabric mod automatically moves the player to this dimension. The server keeps only the player gravity disabled because SM64 supplies the player's motion. Blocks, block entities, redstone, fluids, item stacks, crafting and non-player entities remain normal Minecraft server systems.
