# Universal Modder workflow

Universal Modder is an analysis/orchestration aid for this project.

Use the `mashup-mods`, Minecraft, retro/decomp and game-automation workflows.

## Agent prompt

```text
Build the SM64 x Minecraft crossmod in this repository.

Hard requirements:
- Minecraft Java 1.21.1 + Fabric.
- Keep the player as a native Minecraft player with normal skin, inventory,
  crafting, blocks, tools, weapons and item interactions.
- Recreate SM64's castle/course/star progression as Minecraft gameplay.
- Do not embed an emulator window and do not replace the player with Mario.
- Use the user's own clean SM64 US ROM/decomp output only as local source data.
- Never commit or publish ROM bytes or extracted copyrighted assets.
- Start with Bob-omb Battlefield as the first full vertical slice.
- Prefer data-driven converters and reproducible scripts.
- Keep builds testable after every milestone.
```
