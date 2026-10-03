# SM64 × Minecraft Crossmod

## Target

This project is not a Minecraft-block remake of Super Mario 64.

The real Super Mario 64 world/runtime stays visually Super Mario 64. Mario is replaced by the Minecraft player, while the Minecraft hotbar, inventory and items remain usable.

The visible world is the native SM64 renderer: original 3D castle, courses, textures, skyboxes, enemies, bosses, Stars, doors, paintings, props and moving geometry extracted locally from the user's own ROM.

Minecraft supplies Steve/Alex/your skin, the hotbar, inventory, held items and cross-game mechanics.

The previous block-based prototype is preserved on the legacy-block-prototype branch.

## Current main-branch milestone

Minecraft Java/Fabric sends Steve state through a localhost state/combat bridge to the Super Mario 64 PC runtime. SM64 remains the renderer and world/actor authority; an invisible Mario proxy follows Steve.

Implemented bridge pieces:

- Minecraft player position and rotation are mapped to an invisible Mario proxy.
- The real Mario model is hidden while the bridge is active.
- SM64 continues to render the entire Mario world.
- SM64's own HUD is hidden so Minecraft can own the final HUD.
- The host sends SM64 camera position, camera focus and camera mode back to Minecraft for the compositor.
- Minecraft melee swings are event-based instead of damaging every tick.
- Swords, axes, tools, mace, trident and empty-hand attacks have bridge combat profiles.
- A Minecraft melee swing selects an attackable SM64 actor in front of Steve and injects native SM64 attacked/interacted flags.
- Stars, normal doors and scenery are excluded from melee targeting.
- Bows/crossbows are reserved for the projectile bridge instead of being faked as melee.

Enemy AI/reactions stay in SM64. The bridge tells SM64 that Steve hit an actor; existing SM64 behavior decides how that actor reacts.

The remaining major visual milestone is depth-aware composition: the SM64 color/depth frame becomes the base image, and Minecraft draws Steve, held items, Minecraft blocks/projectiles and the Minecraft HUD into the same view.

See docs/PASSTHROUGH_ARCHITECTURE.md and docs/RENDER_AND_COMBAT.md.

## Requirements

Fabric side: JDK 21, Git and Python 3.

SM64 host on Windows: MSYS2 MinGW64, git, make, python3, mingw-w64-x86_64-gcc, SDL2/GLEW development packages.

Place your own clean Super Mario 64 USA ROM at rom/baserom.us.z64. Expected SHA-1: 9bef1128717f958171a4afac3ed78ee2bb4e86ce.

Run setup-windows.bat to prepare the patched host and build the Fabric mod. The ROM, SM64 checkout, Universal Modder checkout and extracted retail assets are gitignored.


## Test starten

Nach einem erfolgreichen `setup-windows.bat` kannst du unter Windows einfach

```bat
start-test.bat
```

starten. Das Skript öffnet zuerst den gepatchten SM64-Host und danach eine Minecraft-1.21.1-Fabric-Testinstanz mit dem Crossmod.

Öffne anschließend in Minecraft eine Welt. Sobald ein Minecraft-Spieler existiert, beginnt die localhost-Bridge, Steve mit dem unsichtbaren SM64-Mario-Proxy zu synchronisieren.

Hinweis: Der gemeinsame depth-aware 3D-Compositor ist noch nicht fertig. Im aktuellen Test laufen SM64 und Minecraft deshalb noch in getrennten Fenstern; die Bridge für Position, Kamera und Nahkampfangriffe ist bereits aktiv.
