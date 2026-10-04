# Minecraft controls in the visible SM64 window

The visible SM64 window now owns normal Minecraft-style gameplay controls while
the actual Minecraft window remains off-screen.

Implemented:

- mouse look
- left click attack/mine
- right click use/place
- WASD movement through native SM64 physics
- Space jump
- Shift crouch
- Ctrl sprint state
- 1..9 hotbar
- E inventory / close container
- Q drop, Ctrl+Q drop stack
- F swap offhand
- F5 perspective: first person -> third person back -> third person front
- T chat
- slash/command key opens command chat
- Escape closes the active Minecraft screen

When any Minecraft Screen is open, Windows key press/release transitions are
forwarded to that hidden Screen. Unicode text is generated with Win32
`ToUnicode`, so text input follows the user's Windows keyboard layout rather
than assuming US QWERTY. This lets vanilla text fields, chat, Creative search,
anvils and similar GUIs receive keyboard input even though Minecraft itself is
not the focused OS window.
