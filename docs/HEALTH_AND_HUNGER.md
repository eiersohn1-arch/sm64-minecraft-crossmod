# Unified health and hunger

SM64 remains the final death/respawn authority so course deaths, lives and
mission flow continue to use the original game.

Minecraft health changes are nevertheless real gameplay inputs:

1. the integrated Minecraft server is kept at the health value represented by
   SM64;
2. before each correction, the bridge measures any health change Minecraft
   applied since the previous correction;
3. the delta is sent to SM64;
4. negative deltas become SM64 `hurtCounter` ticks;
5. positive deltas become SM64 `healCounter` ticks.

Because the delta is measured *after* Minecraft processes it, vanilla armor,
enchantments, potion effects, mob damage and normal healing affect the amount
that reaches SM64.

Minecraft's own death screen is suppressed by keeping the hidden server player
at a tiny positive health value when SM64 reaches death health. The actual
death/respawn remains the original SM64 flow.

Food is no longer overwritten to full every client tick. The integrated server
keeps normal food/saturation state. Mining/item actions retain vanilla
exhaustion, and the bridge adds sprint-distance exhaustion because authoritative
movement comes from SM64 `setPos` rather than Minecraft's normal travel code.
