# Single visible host window

The crossmod now treats Minecraft as an off-screen guest engine.

## Visible process

`sm64.us.exe` is the normal visible/focused game window.

It owns:

- keyboard movement;
- mouse attack/use;
- SM64 controller mapping;
- the final D3D11 frame;
- the original SM64 game/runtime.

## Hidden guest

Minecraft 1.21.1 still runs as a real Fabric client because that is the safest way to retain the real Minecraft renderer, skin system, inventory, items and GUI.

Once a Minecraft world is loaded and the host is connected, the mod moves Minecraft's GLFW window outside the virtual desktop instead of minimizing it. This keeps the OpenGL framebuffer rendering while removing the second visible game window.

`pauseOnLostFocus` is disabled while the guest runs.

## Host input bridge

SM64 polls keyboard and mouse directly on Windows:

- W/A/S/D -> analog stick
- Space -> A
- left/right mouse -> B plus Minecraft attack/use semantics
- Shift -> Z
- P -> Start
- I/J/K/L -> C buttons
- O/U -> R/L
- 1..9 -> Minecraft hotbar selection
- E -> toggle the real Minecraft inventory

When a Minecraft screen is open, SM64 movement/combat is suspended. Cursor position and mouse press/release events are forwarded to the hidden Minecraft screen, whose rendered GUI then comes back through the normal MCPT overlay layer.

The old click-through SM64-over-Minecraft window mode is archived on `legacy-visible-minecraft-overlay`.
