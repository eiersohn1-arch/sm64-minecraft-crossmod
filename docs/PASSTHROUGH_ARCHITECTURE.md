# SM64 runtime + Minecraft passthrough

The old Minecraft-block recreation is archived on `legacy-block-prototype`.

The current architecture follows Universal Modder's passthrough pattern: two real game runtimes execute at once and exchange state, events and rendered layers.

## SM64 is authoritative for the whole original game

SM64 owns:

- Peach's Castle and every original course/secret stage
- all original geometry, textures, actors, bosses and music
- movement physics and collision
- swimming, slopes, quicksand, cannons, poles and moving platforms
- doors, paintings, warps and cutscenes
- mission selection
- all 120 Stars and course/secret progression
- Bowser keys and Grand Star
- save data, death and respawn

Mario still exists internally because the original runtime expects him. His model is hidden while connected; his native state is the collision/interaction body represented visually by Steve.

## Minecraft contributes the player presentation and item layer

Minecraft supplies:

- Steve/Alex/custom skin
- Minecraft hotbar and inventory
- held tools and weapons
- HUD
- Minecraft item-use/attack events
- future Minecraft projectiles, blocks and effects

Minecraft does **not** drive Mario by teleporting coordinates. It sends input. SM64 runs its normal controller/action/physics code, then sends the resulting authoritative player and camera pose back to Minecraft for rendering.

## Universal Modder transport

The exact reference repository is cloned with:

`git clone https://github.com/rehan-remade/universal-modder`

Reference example:

`examples/minecraft-gta5-passthrough`

The crossmod uses the same split:

- localhost WebSocket on `127.0.0.1:25599` for camera/state/input/item events;
- named shared-memory ring `Local\MCPassthroughFrame` for Minecraft colour/depth/overlay frames;
- host-side depth compositor;
- event adapters that turn Minecraft item actions into host-game effects.

The setup copies Universal Modder's own `ws.h` and `ws.cpp` directly from the clone into the SM64 build.
