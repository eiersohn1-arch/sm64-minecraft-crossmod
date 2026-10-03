# Minecraft item adapters

Minecraft items are layered on top of the original SM64 mission runtime rather than replacing it.

Current host adapters:

- swords / axes / mace / tools / empty hand: one native SM64 attack per Minecraft left-click
- bow / crossbow: right-click use event performs a forward SM64 enemy hit check
- trident: left-click keeps melee behavior; right-click uses the ranged adapter
- TNT: right-click creates an SM64-side five-block-radius attack pulse against attackable actors

The original B-button action still runs as well. This is important for mission mechanics that require Mario's native grab/throw/use logic, such as Big Bob-omb and Bowser.

The adapter deliberately targets only objects with SM64 enemy/breakable interaction types, so Stars, normal doors and scenery are not treated like Minecraft mobs.

Visual Minecraft projectiles and placeable-block collision are separate compositor/collision milestones; the current ranged/TNT adapters make the gameplay effect functional first.
