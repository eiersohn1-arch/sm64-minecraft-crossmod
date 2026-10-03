# Overlay alpha invariant

The Minecraft overlay layer must be transparent everywhere that Minecraft did not draw hand/HUD/GUI content.

On Minecraft 1.21.1 OpenGL, `glClear` obeys the current colour-write mask and scissor state. A stale alpha write mask can therefore turn a requested transparent clear into an opaque black frame. The exporter now forces:

- full RGBA colour writes;
- scissor disabled for the clear;
- `glClearColor(0,0,0,0)`;
- then restores the previous OpenGL write/scissor state.

The SM64 compositor also rejects a fully opaque, exactly-black clear pixel as a compatibility safeguard. This prevents the failure mode where the player sees only a black screen plus Minecraft HUD while the native SM64 frame is actually underneath.
