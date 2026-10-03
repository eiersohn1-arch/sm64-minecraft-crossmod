# Universal Modder workflow

This project now uses Universal Modder as the concrete passthrough reference, not just as an analysis aid.

Clone used by setup:

```
git clone https://github.com/rehan-remade/universal-modder
```

Primary reference:

`examples/minecraft-gta5-passthrough`

Relevant skill:

`skills/mashup-mods/SKILL.md`

## Project mapping

Universal Modder example | SM64 × Minecraft
---|---
Minecraft Fabric guest | Minecraft 1.21.1 Fabric guest
GTA host plugin | patched native SM64-port host
localhost WebSocket | localhost WebSocket on the same 25599 port
`Local\MCPassthroughFrame` | same named shared-memory contract
ReShade host compositor | native SM64 D3D11 compositor
GTA camera/player state | SM64 camera/player/progression state
Minecraft explosion/projectile events | Minecraft weapon/TNT -> SM64 actor events

SM64 remains the source of truth for the complete original game's 120-Star progression. Minecraft remains the visible player/item/HUD layer.
