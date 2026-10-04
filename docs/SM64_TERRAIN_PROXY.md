# Native SM64 terrain proxy for Minecraft entities

The hybrid already mirrors real Minecraft block `VoxelShape` collision into
SM64. This file documents the reverse path.

Every few SM64 frames the native host samples the current static SM64 floor
around Mario on a 17 × 17 Minecraft-block grid. The samples are sent to the
hidden Minecraft guest.

The integrated server creates invisible `minecraft:barrier` blocks one block
below the sampled floor height. They are never rendered by the passthrough
scene and they are excluded from the Minecraft->SM64 block collision mirror.

Purpose:

- Minecraft mobs have local ground instead of falling into the void;
- arrows/tridents/dropped items can contact the local SM64 ground;
- vanilla entity physics can run in the overlay dimension;
- user-placed Minecraft blocks remain separate real blocks.

This is deliberately a local collision shell, not a visual conversion of SM64
into Minecraft blocks. Original SM64 geometry/textures remain the only visible
level. Complex slopes and vertical walls are still native-SM64 authoritative;
the proxy is an entity-physics approximation around the player.
