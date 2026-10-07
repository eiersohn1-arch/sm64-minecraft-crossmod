#!/usr/bin/env python3
"""Minimal SM64 delta on top of Universal Modder's real Minecraft passthrough.

Universal Modder remains the source of truth.  We keep its HostLink,
FrameExporter, SharedMemory, WorldBridge and Minecraft renderer intact.  The
delta only converts GTA's special drive mode into ordinary Minecraft survival
controls while the SM64 window owns focus.
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
    'import net.minecraft.client.Minecraft;\n',
    'import net.minecraft.client.Minecraft;\n'
    'import net.minecraft.client.input.MouseButtonEvent;\n'
    'import net.minecraft.client.input.MouseButtonInfo;\n',
)
replace_once(
    client_input,
    'final class ClientInput {\n\tprivate ClientInput() {\n',
    'final class ClientInput {\n'
    '\tprivate static double hostPointerX = 0.5;\n'
    '\tprivate static double hostPointerY = 0.5;\n'
    '\tprivate static int activeUiButton = 0;\n\n'
    '\tprivate ClientInput() {\n',
)
replace_once(
    client_input,
    '		switch (m.get("t").getAsString()) {\n			case "key" -> {',
    '		switch (m.get("t").getAsString()) {\n'
    '			case "pointer" -> {\n'
    '				double oldX = hostPointerX;\n'
    '				double oldY = hostPointerY;\n'
    '				hostPointerX = Math.clamp(m.get("x").getAsDouble(), 0.0, 1.0);\n'
    '				hostPointerY = Math.clamp(m.get("y").getAsDouble(), 0.0, 1.0);\n'
    '				if (minecraft.gui.screen() != null && activeUiButton != 0) {\n'
    '					double x = hostPointerX * minecraft.getWindow().getGuiScaledWidth();\n'
    '					double y = hostPointerY * minecraft.getWindow().getGuiScaledHeight();\n'
    '					double dx = (hostPointerX - oldX) * minecraft.getWindow().getGuiScaledWidth();\n'
    '					double dy = (hostPointerY - oldY) * minecraft.getWindow().getGuiScaledHeight();\n'
    '					MouseButtonEvent event = new MouseButtonEvent(x, y, new MouseButtonInfo(activeUiButton, 0));\n'
    '					minecraft.gui.screen().mouseDragged(event, dx, dy);\n'
    '				}\n'
    '			}\n'
    '			case "uibutton" -> {\n'
    '				if (m.has("x")) hostPointerX = Math.clamp(m.get("x").getAsDouble(), 0.0, 1.0);\n'
    '				if (m.has("y")) hostPointerY = Math.clamp(m.get("y").getAsDouble(), 0.0, 1.0);\n'
    '				if (minecraft.gui.screen() != null) {\n'
    '					int button = m.get("b").getAsInt();\n'
    '					boolean down = m.get("down").getAsBoolean();\n'
    '					double x = hostPointerX * minecraft.getWindow().getGuiScaledWidth();\n'
    '					double y = hostPointerY * minecraft.getWindow().getGuiScaledHeight();\n'
    '					MouseButtonEvent event = new MouseButtonEvent(x, y, new MouseButtonInfo(button, 0));\n'
    '					if (down) {\n'
    '						activeUiButton = button;\n'
    '						minecraft.gui.screen().afterMouseAction();\n'
    '						minecraft.gui.screen().mouseClicked(event, false);\n'
    '					} else {\n'
    '						minecraft.gui.screen().mouseReleased(event);\n'
    '						if (activeUiButton == button) activeUiButton = 0;\n'
    '					}\n'
    '				}\n'
    '			}\n'
    '			case "move" -> {\n'
    '				boolean gameplay = minecraft.gui.screen() == null;\n'
    '				minecraft.options.keyUp.setDown(gameplay && m.get("f").getAsBoolean());\n'
    '				minecraft.options.keyDown.setDown(gameplay && m.get("b").getAsBoolean());\n'
    '				minecraft.options.keyLeft.setDown(gameplay && m.get("l").getAsBoolean());\n'
    '				minecraft.options.keyRight.setDown(gameplay && m.get("r").getAsBoolean());\n'
    '				minecraft.options.keyJump.setDown(gameplay && m.get("jump").getAsBoolean());\n'
    '				minecraft.options.keyShift.setDown(gameplay && m.get("sneak").getAsBoolean());\n'
    '				minecraft.options.keySprint.setDown(gameplay && m.get("sprint").getAsBoolean());\n'
    '			}\n'
    '			case "look" -> {\n'
    '				if (player != null && minecraft.gui.screen() == null) {\n'
    '					double sensitivity = minecraft.options.sensitivity().get();\n'
    '					double base = sensitivity * 0.6 + 0.2;\n'
    '					double scale = base * base * base * 8.0;\n'
    '					player.turn(m.get("dx").getAsDouble() * scale, m.get("dy").getAsDouble() * scale);\n'
    '				}\n'
    '			}\n'
    '			case "key" -> {',
)

# Make the existing Universal Modder scroll action operate on the actual
# Minecraft screen when inventory/crafting/etc. is open; otherwise it keeps
# its original hotbar behavior.
replace_once(
    client_input,
    '			case "scroll" -> {\n'
    '				if (player != null) {\n'
    '					Inventory inventory = player.getInventory();\n'
    '					int size = Inventory.getSelectionSize();\n'
    '					inventory.setSelectedSlot(Math.floorMod(inventory.getSelectedSlot() - m.get("d").getAsInt(), size));\n'
    '				}\n'
    '			}\n',
    '			case "scroll" -> {\n'
    '				double amount = m.get("d").getAsDouble();\n'
    '				if (minecraft.gui.screen() != null) {\n'
    '					double x = hostPointerX * minecraft.getWindow().getGuiScaledWidth();\n'
    '					double y = hostPointerY * minecraft.getWindow().getGuiScaledHeight();\n'
    '					minecraft.gui.screen().mouseScrolled(x, y, 0.0, amount);\n'
    '					minecraft.gui.screen().afterMouseAction();\n'
    '				} else if (player != null) {\n'
    '					Inventory inventory = player.getInventory();\n'
    '					int size = Inventory.getSelectionSize();\n'
    '					inventory.setSelectedSlot(Math.floorMod(inventory.getSelectedSlot() - (int)Math.signum(amount), size));\n'
    '				}\n'
    '			}\n',
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



# 5) Keep the real Minecraft world/session in survival on every join.  The UM
# GTA demo starts from creative-flight assumptions; the SM64 mashup must not.
world_bridge = ROOT / "generated" / "minecraft-guest" / "src" / "main" / "java" / "dev" / "rehan" / "passthrough" / "WorldBridge.java"
if not world_bridge.is_file():
    raise SystemExit("Universal Modder WorldBridge.java missing.")

# No source copy is replaced here: WorldBridge remains the UM implementation.
# The existing guest patch already switches LevelSettings to SURVIVAL and
# disables creative flight in PlayerSync/PassthroughClient.

print("Universal Modder guest kept intact; SM64 survival-control delta applied.")

