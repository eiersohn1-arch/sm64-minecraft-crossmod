# D3D11 compositor

The Windows SM64 build uses its native Direct3D 11 renderer as the host compositor.

This follows the same passthrough pattern as
`universal-modder/examples/minecraft-gta5-passthrough`:

1. Minecraft renders a guest frame.
2. Minecraft publishes world colour, world depth and a separate hand/HUD layer.
3. The host reads the latest completed slot from named shared memory.
4. The host compares guest depth with its own depth.
5. Minecraft content is blended only where it belongs in front of the host scene.
6. The screen-space Minecraft overlay is drawn last.

## Shared-memory contract

The transport is the same MCPT layout used by Universal Modder's worked example:

- mapping: `Local\MCPassthroughFrame`
- magic: `MCPT`
- three rotating slots
- odd sequence while a slot is being written
- even sequence when complete
- publish counter + latest slot
- world RGBA8
- world depth float32
- overlay RGBA8
- near/far/FOV and camera pose stored with the rendered frame

The Minecraft 1.21.1 renderer differs from Universal Modder's current Minecraft version, so this project uses the 1.21.1 OpenGL readback API while preserving the same transport contract.

## SM64 host integration

SM64's depth texture is exposed as a D3D11 shader resource. The compositor therefore knows which surface is in front instead of doing a flat picture overlay.

Expected result:

- the genuine SM64 frame is the base scene;
- Steve and Minecraft 3D content can appear inside it;
- an SM64 wall can occlude Steve;
- Minecraft sky/vanilla terrain do not replace the SM64 scene;
- Minecraft hand, hotbar, inventory and HUD remain screen-space overlays.

Because SM64-port's renderer source is available, this compositor lives directly in its D3D11 backend. This is equivalent to the ReShade add-on role in the GTA example, without requiring ReShade.

## Current single-window test

For the present Minecraft-1.21.1 test harness, the SM64 host window becomes a borderless click-through overlay aligned to Minecraft's client area after the first shared frame is published. Minecraft stays focused for normal keyboard, mouse, inventory and hotbar input.

A later host-input route can move focus fully to the host, like the GTA example, without changing the WebSocket or shared-memory protocol.


## Camera reprojection

The compositor also ports the latency correction used by Universal Modder's Minecraft × GTA example.

Every published Minecraft frame stores the exact camera position, yaw, pitch and FOV that rendered it. SM64 independently exposes the camera pose it is rendering now. When those poses differ, the compositor:

1. reconstructs the current SM64 camera ray for each screen pixel;
2. transforms that ray into the older Minecraft-frame camera space;
3. marches the ray against Minecraft's exported depth texture;
4. refines the first depth crossing;
5. samples Minecraft colour at the reprojected coordinate;
6. compares the recovered Minecraft depth against the native SM64 depth.

The Minecraft HUD/hand overlay is intentionally not reprojected; it remains screen-space.

This is the same core 6-DoF depth-reprojection idea as `MCPassthrough.fx`, adapted to SM64's native D3D11 compositor.
