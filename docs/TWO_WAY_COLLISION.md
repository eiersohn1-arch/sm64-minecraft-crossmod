# SM64 -> Minecraft dynamic collision

Minecraft is the locomotion authority, so it needs a usable collision
representation of the original SM64 level even though that level is not made
of Minecraft blocks.

## Dynamic proxy block

The mod registers an invisible internal block:

`sm64cross:sm64_collision`

It has no visible render shape and no selection outline. Its collision shape is
looked up dynamically by block position and can contain several VoxelShapes.
A real player-created Minecraft block always takes precedence over this proxy.

## Floors

Each nearby one-block X/Z cell is sampled at four quarter-cell positions.
Every sample keeps its fractional height inside the Minecraft block. Sloped
Mario geometry therefore becomes a 2x2 stepped micro-surface instead of being
rounded to a full Barrier cube.

## Walls

SM64 wall collision provides the triangle plane normal and origin offset. The
bridge solves that plane at the sampled height and sends a thin vertical
VoxelShape at the corresponding local X or Z coordinate. This avoids turning
an entire one-meter cell solid just because a wall passes through it.

## Ceilings

Nearby ceilings are represented as the upper slice of a block beginning at the
actual SM64 ceiling height.

## Update rate

The local shell is refreshed much more frequently than the old Barrier proxy,
so sprinting/jumping Minecraft movement is less likely to outrun the streamed
course collision.

## Reverse direction

Real Minecraft block VoxelShapes are still published back to SM64 as dynamic
native collision surfaces. The special proxy blocks are excluded from that
publisher, preventing a collision feedback loop.
