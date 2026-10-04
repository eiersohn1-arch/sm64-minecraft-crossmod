# Native-resolution smooth HUD

The hidden Minecraft window no longer stays at a fixed 1280x720 after the
passthrough connection is active.

SM64 publishes its current client-area width/height with the camera packet.
The off-screen Minecraft GLFW window follows that size (up to the existing
3840x2160 MCPT limit), so Minecraft world geometry, held items, GUI and hotbar
are exported at approximately 1:1 host resolution instead of being enlarged
by the D3D11 compositor.

## Smooth vitals

While connected, the vanilla 9x9 pixel-art heart/food/armor/air strip is
suppressed and replaced with flat-resolution bars:

- health;
- absorption;
- hunger;
- armor;
- air when relevant.

The actual Minecraft values remain authoritative. Hotbar, item sprites, XP,
effects, chat, inventories and all other Minecraft UI stay untouched.

The SM64 progression readout is also reduced to a compact flat panel rather
than imitating the original N64 bitmap HUD.
