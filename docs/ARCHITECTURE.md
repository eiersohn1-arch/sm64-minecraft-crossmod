# Architecture

This is not an emulator window inside Minecraft.

The Minecraft player stays native: skin, movement, inventory, hotbar, armor, tools, weapons, blocks, crafting and item interactions.

SM64 becomes the adventure layer: castle hub, painting portals, courses, mission objectives, stars, star-gated doors, bosses and final completion.

## First milestone

The base mod includes a persistent 0–120 star counter and a Power Star item.

Test with:

```
/give @s sm64cross:power_star
/sm64
/sm64 stars
/sm64 star add 1
/sm64 star set 0
/sm64 level list
/sm64 level info bob_omb_battlefield
```

The first complete vertical slice will be Bob-omb Battlefield.
