# Minecraft locomotion authority

The crossmod no longer uses Super Mario 64's locomotion system while the
Minecraft guest is connected.

## Authority

Vanilla Minecraft now owns:

- walking and strafing;
- acceleration/friction;
- jumping and falling;
- sprinting;
- crouching;
- Minecraft block collision;
- the streamed invisible SM64 terrain collision shell;
- movement speed effects/enchantments;
- hunger exhaustion caused by normal movement.

The visible SM64 window still owns the OS keyboard/mouse. It sends the key
states and camera yaw/pitch to the hidden Minecraft client, where vanilla
KeyMappings drive the real LocalPlayer.

Minecraft publishes its actual player position and velocity back to SM64 every
tick.

## Mario is only a mission proxy

When connected, `execute_mario_action` does not execute stationary, moving,
airborne or submerged locomotion groups.

The hidden Mario proxy is snapped to Minecraft's authoritative pose and is
used only for original SM64 systems that need a MarioState:

- stars and object interactions;
- paintings/warps;
- doors and mission triggers;
- enemy interactions;
- health/progression;
- automatic/object/cutscene state machines.

Automatic/object/cutscene actions are allowed to advance, but their movement
is immediately discarded by reapplying the Minecraft pose.

On a new SM64 level/area/act, authority briefly waits at the original native
spawn. The Minecraft player is teleported to that spawn exactly once, then
Minecraft locomotion becomes authoritative again.
