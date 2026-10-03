# Native-authority architecture

The previous bridge moved Mario by directly copying Minecraft coordinates into the SM64 Mario state. That was useful to prove the connection, but it bypassed too much of Super Mario 64.

The main branch now uses **SM64-native authority**.

## Rule

SM64 owns:

- player movement physics
- floor/wall/ceiling collision
- slopes and sliding
- water and swimming
- quicksand
- cannons
- poles and trees
- doors
- paintings and warps
- moving platforms
- caps
- Stars and Red Coins
- Bowser stages
- death/respawn
- cutscenes
- all normal SM64 level scripts

Minecraft owns:

- visible Steve/Alex/custom skin
- hotbar and inventory
- Minecraft held items
- item selection
- Minecraft combat additions
- future blocks/projectiles/TNT additions

## Input path

Minecraft sends W/A/S/D, jump, sneak, use and item/combat state to the localhost bridge.

The bridge writes those movement controls into SM64's real `gPlayer1Controller` **after normal controller polling**. SM64 then runs the unchanged native Mario action system.

The Mario model is hidden only after SM64 finishes the native movement/action update. The invisible Mario remains the authoritative collision and interaction body for Steve.

## Why this scales to the whole game

Because the bridge does not manually recreate course physics or progression, Peach's Castle and every normal course can use the original SM64 runtime. A new course does not need a custom movement implementation.

The remaining large systems are rendering/composition and Minecraft-item event adapters, not rebuilding all 120 Stars by hand.
