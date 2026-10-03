# Whole-game contract

The crossmod does **not** recreate Super Mario 64 mission-by-mission.

Instead, the original SM64 runtime remains authoritative for the complete game.

## Preserved original systems

The bridge leaves the original SM64 level scripts and progression code intact, including:

- all 15 main courses
- castle grounds, interior, basement, upstairs and courtyard
- Bowser in the Dark World
- Bowser in the Fire Sea
- Bowser in the Sky
- Princess's Secret Slide
- Secret Aquarium
- Wing Cap, Metal Cap and Vanish Cap stages
- Wing Mario Over the Rainbow
- all normal mission Stars
- 100-coin Stars
- red-coin Stars
- castle secret Stars
- Bowser keys and Grand Star
- star doors and key doors
- cannon unlocks
- cap switches
- Dire Dire Docks progression
- moat drain progression
- save files and collected-star flags
- death, respawn, warps and credits

That is how the project scales to the complete 120-Star game: SM64 itself runs the missions.

## Minecraft controls -> native N64 controls

- WASD -> analog stick
- Space -> A
- Left click / right click -> B/use
- Shift -> Z
- P -> Start/Pause
- I/J/K/L -> C-Up/C-Left/C-Down/C-Right
- O -> R
- U -> L

Minecraft weapon metadata is layered on top of the native B action, so original mission interactions such as grabbing Big Bob-omb or Bowser remain possible.

## Automatic integrity check

`tools/verify_whole_game.py` checks every setup/build and fails if the crossmod accidentally modifies:

- any original `levels/` file
- `level_update.c`
- `save_file.c`
- `star_select.c`
- original behavior data

It also verifies the complete level directory set and the 15 main course definitions.

The remaining work for the final user experience is the renderer/compositor and richer Minecraft-item adapters. The mission/progression authority itself is the original full SM64 game.
