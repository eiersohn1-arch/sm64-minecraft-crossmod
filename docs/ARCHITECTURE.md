# Architecture contract

The clean rebuild follows Universal Modder `mashup-mods` Pattern 2.

## Authority
Minecraft owns normal locomotion, look, inventory, item use, mining, placement, hunger and its HUD.
SM64 owns its world, mission/progression objects, stars, warps, enemies and level rendering.

## Transport
Control/state stays on 127.0.0.1. High-bandwidth rendered layers use the MCPT shared-memory ring from the Universal Modder worked example.

## Rendering
Minecraft exports world RGBA + depth before the hand, then exports hand/HUD/screens as a separate transparent overlay. The SM64 host depth-tests the world layer against its own depth and draws the overlay last.

## Collision
The host sends nearby walkable/collidable geometry to Minecraft. The guest uses invisible collision so vanilla Minecraft physics remains authoritative. Minecraft-created solids/events are sent back to the host.

## Oracle rule
Do not add full gameplay until a fake host proves camera alignment, depth occlusion, input and collision. Every later milestone keeps that oracle green.
