# Minecraft controls exposed by the SM64 host

The visible SM64 window now forwards the core Minecraft controls that would
normally belong to the hidden GLFW window.

- mouse move: Minecraft-style free look
- left click: attack/mine
- right click: use/place/eat/drink/charge
- mouse wheel: hotbar scroll
- 1..9: hotbar selection
- E: inventory/creative inventory
- Q: drop, Ctrl+Q: drop stack
- F: swap main/off hand
- T: chat
- /: command chat
- F1: hide/show Minecraft HUD (the SM64 STAR/COINS/LIVES overlay follows it)
- F5: first person -> third-person back -> third-person front

First-person hand/item rendering is the real vanilla ItemInHandRenderer.
Third-person Steve/skin/armor/cape/elytra/held items are the real vanilla
player renderer.

The local player's visual pose is now also derived from the native SM64 action
flags. Swimming actions use Minecraft's SWIMMING pose, short-hitbox/crouch
actions use CROUCHING, and ordinary actions use STANDING. Real host motion is
fed into the client entity's delta movement so vanilla animation code has
movement information even though SM64 remains the authoritative physics body.
