# D3D11 compositor

The Windows SM64 build uses its native Direct3D 11 renderer as the final visible window.

Minecraft exports three layers every frame:

1. transparent Minecraft 3D colour (Steve, held items, future placed blocks/projectiles)
2. Minecraft depth
3. screen-space overlay (hotbar, hearts/hunger, menus)

The patched SM64 D3D11 backend exposes the native SM64 depth buffer as a shader resource. At the end of every SM64 frame, a fullscreen compositor compares Minecraft depth with SM64 depth.

Result:

- SM64 remains the base image.
- Steve and Minecraft 3D objects appear only where their depth is in front of the SM64 surface.
- Steve can therefore disappear behind castle walls, terrain and props.
- Minecraft sky/background never replaces SM64 because depth-clear pixels are discarded.
- Minecraft hotbar/HUD is always blended on top.
- Different Minecraft/SM64 window aspect ratios are corrected from the shared vertical FOV.

The current implementation uses the temp-file mapping `sm64cross_frame.bin` so Java 21 and the MinGW SM64 host can exchange frames without JNI/JNA or third-party runtime DLLs.

This is the first in-host compositor milestone. It is intentionally kept inside the original SM64 renderer so the final game does not require ReShade.


## Single visible play surface

Once Minecraft has published its native Windows handle and content-area rectangle, the SM64 window switches into a borderless click-through overlay positioned exactly above the Minecraft client area.

Minecraft deliberately remains the focused window underneath. This means normal Minecraft keyboard/mouse input, hotbar selection and inventory screens keep working, while the player sees the composited SM64 output above it. The overlay uses `WS_EX_NOACTIVATE` and `WS_EX_TRANSPARENT`; when Minecraft loses focus the SM64 overlay hides, so it does not cover other desktop applications.
