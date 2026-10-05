#!/usr/bin/env python3
"""SM64 gameplay delta on top of Universal Modder's passthrough guest.

Universal Modder remains the source of truth.  This delta only adapts the
worked GTA passthrough's special "drive" mode into normal Minecraft gameplay
for SM64:
- Steve stays visible in third person;
- normal Minecraft movement keys are accepted from the focused SM64 window;
- mouse deltas turn the real LocalPlayer using Minecraft-style sensitivity;
- creative flight is disabled so vanilla gravity/jump/sprint/sneak apply;
- player position, velocity and look are sent back to SM64 every frame;
- the passthrough world starts in survival so hearts/hunger/item behaviour are real.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / "generated" / "minecraft-guest"
CLIENT = GUEST / "src" / "client" / "java" / "dev" / "rehan" / "passthrough" / "client"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Universal Modder marker changed in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if not CLIENT.is_dir():
    raise SystemExit("Run tools/sync_um_reference.py first.")

# 1) GTA has a camera-near-head heuristic that can hide Steve.  For SM64 a
# requested third-person view must always render the player model.
camera = CLIENT / "mixin" / "CameraMixin.java"
replace_once(
    camera,
    "this.detached = !p.firstPerson() && !inside;",
    "this.detached = !p.firstPerson(); // SM64: requested third person always renders Steve",
)

# 2) Feed real Minecraft movement and mouse look from the focused SM64 window.
client_input = CLIENT / "ClientInput.java"
replace_once(
    client_input,
    '		switch (m.get("t").getAsString()) {\n			case "key" -> {',
    '		switch (m.get("t").getAsString()) {\n'
    '			case "move" -> {\n'
    '				minecraft.options.keyUp.setDown(m.get("f").getAsBoolean());\n'
    '				minecraft.options.keyDown.setDown(m.get("b").getAsBoolean());\n'
    '				minecraft.options.keyLeft.setDown(m.get("l").getAsBoolean());\n'
    '				minecraft.options.keyRight.setDown(m.get("r").getAsBoolean());\n'
    '				minecraft.options.keyJump.setDown(m.get("jump").getAsBoolean());\n'
    '				minecraft.options.keyShift.setDown(m.get("sneak").getAsBoolean());\n'
    '				minecraft.options.keySprint.setDown(m.get("sprint").getAsBoolean());\n'
    '			}\n'
    '			case "look" -> {\n'
    '				if (player != null) {\n'
    '					double sensitivity = minecraft.options.sensitivity().get();\n'
    '					double base = sensitivity * 0.6 + 0.2;\n'
    '					double scale = base * base * base * 8.0;\n'
    '					player.turn(m.get("dx").getAsDouble() * scale, m.get("dy").getAsDouble() * scale);\n'
    '				}\n'
    '			}\n'
    '			case "key" -> {',
)

# 3) In Universal Modder's original drive mode Minecraft is intentionally
# airborne for GTA elytra flight.  SM64 uses the same mode for ordinary
# walking, so retain vanilla onGround/gravity, honour F5 first/third person,
# and report rotation too.
player_sync = CLIENT / "PlayerSync.java"
replace_once(
    player_sync,
    'if (minecraft.options.getCameraType() != CameraType.THIRD_PERSON_BACK) {\n'
    '\t\t\t\tminecraft.options.setCameraType(CameraType.THIRD_PERSON_BACK);\n'
    '\t\t\t}',
    'CameraType driveCamera = p.firstPerson() ? CameraType.FIRST_PERSON : CameraType.THIRD_PERSON_BACK;\n'
    '\t\t\tif (minecraft.options.getCameraType() != driveCamera) {\n'
    '\t\t\t\tminecraft.options.setCameraType(driveCamera);\n'
    '\t\t\t}',
)
replace_once(
    player_sync,
    '			// airborne: with no collision onGround never updates, and the server cancels a grounded player\'s glide\n'
    '			player.setOnGround(false);\n\n'
    '			// where the player is drawn this frame, how fast that moves (the slope of the tick interpolation, per\n',
    '			Abilities driveAbilities = player.getAbilities();\n'
    '			if (driveAbilities.flying) {\n'
    '				driveAbilities.flying = false;\n'
    '				player.onUpdateAbilities();\n'
    '			}\n\n'
    '			// where the player is drawn this frame, how fast that moves (the slope of the tick interpolation, per\n',
)
replace_once(
    player_sync,
    'Passthrough.events.accept(String.format(Locale.ROOT, "{\\\"t\\\":\\\"mcpos\\\",\\\"pos\\\":[%.4f,%.4f,%.4f],\\\"vel\\\":[%.3f,%.3f,%.3f],\\\"tn\\\":%d,\\\"fly\\\":%b}",\n'
    '				at.x, at.y, at.z, vx, vy, vz, System.nanoTime(), player.isFallFlying()));',
    'Passthrough.events.accept(String.format(Locale.ROOT, "{\\\"t\\\":\\\"mcpos\\\",\\\"pos\\\":[%.4f,%.4f,%.4f],\\\"vel\\\":[%.3f,%.3f,%.3f],\\\"r\\\":[%.3f,%.3f],\\\"tn\\\":%d,\\\"fly\\\":%b}",\n'
    '				at.x, at.y, at.z, vx, vy, vz, player.getYRot(), player.getXRot(), System.nanoTime(), player.isFallFlying()));',
)

# 4) The reference world is creative and starts flying because GTA uses it as
# an overlay sandbox.  For SM64 gameplay, use real survival rules.
passthrough_client = CLIENT / "PassthroughClient.java"
replace_once(
    passthrough_client,
    'LevelSettings settings = new LevelSettings("Passthrough", GameType.CREATIVE,',
    'LevelSettings settings = new LevelSettings("Passthrough", GameType.SURVIVAL,',
)
replace_once(
    passthrough_client,
    '			player.getAbilities().flying = true;\n',
    '			player.getAbilities().flying = false;\n',
)

print("Applied SM64 Minecraft-gameplay delta to Universal Modder guest.")
