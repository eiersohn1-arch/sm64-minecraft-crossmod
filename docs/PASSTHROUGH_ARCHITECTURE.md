# Minecraft-authoritative SM64 passthrough

The crossmod runs the real Minecraft 1.21.1 client/integrated server and the
real SM64 PC runtime at the same time, but assigns each system one clear owner.

## Minecraft owns moment-to-moment player gameplay

Minecraft owns:

- WASD movement, acceleration, friction and gravity;
- jump, sprint and crouch;
- mouse yaw/pitch using the player's real Minecraft sensitivity and invert-Y;
- first/third person player rendering;
- hand, hotbar, inventory and GUI;
- ItemStacks, tools, weapons, blocks and BlockEntities;
- mining, placement, use, food, hunger and normal Minecraft entities.

The SM64 host captures input because it is the focused visible window, but it
forwards raw movement state and raw mouse delta into Minecraft. It does not run
a second imitation movement controller.

## SM64 owns its original world and progression

SM64 still owns the authored game:

- Peach's Castle and every original course;
- original geometry, textures, objects, enemies and bosses;
- stars, acts, Red Coins, Bowser keys and save data;
- doors, paintings, warps and cutscenes;
- music and original mission logic.

Mario remains as an invisible native interaction/mission proxy. Minecraft's
real player position and velocity are mirrored into that proxy; native SM64
code can process stars, doors and object interactions, then the proxy is snapped
back to Minecraft's authoritative pose.

## SM64 geometry becomes Minecraft collision, not Minecraft scenery

The original level is not rebuilt visually from cubes. Instead the host samples
nearby SM64 collision and streams invisible dynamic Minecraft VoxelShapes:

- four sub-cell floor samples per block for smoother slopes;
- thin wall slices located on the SM64 wall plane;
- exact-height ceiling slices.

The special `sm64cross:sm64_collision` block renders nothing, has no selection
outline and is replaceable by real player-built blocks. Its collision shape is
dynamic, so vanilla Minecraft movement and entities physically inhabit the
native SM64 course without showing a voxel copy of that course.

Minecraft blocks are streamed in the opposite direction as their real
VoxelShape AABBs so the SM64 mission proxy and native objects can collide with
player construction.

## Rendering

The hidden Minecraft client exports world colour/depth plus a transparent
hand/HUD/GUI layer through `Local\\MCPassthroughFrame`. SM64's D3D11 renderer
depth-composites those layers into the single visible SM64 window.

Transport follows the Universal Modder passthrough pattern:

- localhost WebSocket for state/events/input/collision;
- shared-memory frame ring for GPU output;
- host-side depth composition and reprojection.
