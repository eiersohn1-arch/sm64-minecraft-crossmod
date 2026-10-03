# SM64 × Minecraft Crossmod

## Target

This project is **not** a Minecraft-block remake of Super Mario 64.

The target is:

> The real Super Mario 64 world/runtime stays visually Super Mario 64.  
> Mario is replaced by the Minecraft player, while the Minecraft hotbar,
> inventory and items remain usable.

That means the visible game should contain the original SM64 castle, courses, textures, skyboxes, enemies, bosses, Stars, doors, paintings and other SM64 content extracted locally from the user's own ROM.

The Minecraft side supplies Steve/Alex/your skin, hotbar, inventory and Minecraft items.

The previous block-based prototype has been preserved on the branch:

```text
legacy-block-prototype
```

Do not use that branch for the final target.

## Current main-branch milestone

The project has been pivoted to a **passthrough mashup**:

```text
Minecraft Java / Fabric
  Steve + hotbar + inventory + items
             |
             | localhost bridge
             v
SM64 PC runtime
  original SM64 renderer + world + actors
  hidden Mario proxy follows Steve
```

The first bridge code is now present on both sides:

- Fabric transmits Minecraft player position, camera rotation, held item, attack/use state, health and hunger.
- The patched SM64 host listens on localhost.
- When connected, SM64 hides Mario.
- The hidden Mario proxy follows Minecraft's player position.
- SM64's own world renderer remains responsible for the Mario world.
- SM64 HUD is hidden while the Minecraft bridge is active.

The next rendering milestone is depth-aware frame composition so Minecraft renders only Steve, Minecraft blocks/items and the native Minecraft HUD over the SM64 frame.

See `docs/PASSTHROUGH_ARCHITECTURE.md`.

## Requirements

For the Fabric side:

- JDK 21
- Git
- Python 3

For the SM64 host on Windows:

- MSYS2 MinGW64
- `git`
- `make`
- `python3`
- `mingw-w64-x86_64-gcc`
- SDL2/GLEW development packages

And your own clean Super Mario 64 USA ROM:

```text
rom/baserom.us.z64
```

Expected SHA-1:

```text
9bef1128717f958171a4afac3ed78ee2bb4e86ce
```

## Prepare the new passthrough project

Run:

```bat
setup-windows.bat
```

The script verifies the ROM, prepares the patched SM64 PC host, downloads Universal Modder locally and builds the Fabric mod.

The ROM, SM64 checkout, Universal Modder checkout and extracted retail assets are gitignored.
