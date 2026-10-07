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
ADAPTER = ROOT / "guest_adapter"
MAIN = GUEST / "src" / "main" / "java" / "dev" / "rehan" / "passthrough"
CLIENT = GUEST / "src" / "client" / "java" / "dev" / "rehan" / "passthrough" / "client"
RES = GUEST / "src" / "main" / "resources"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Universal Modder marker changed in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if not CLIENT.is_dir():
    raise SystemExit("Run tools/sync_um_reference.py first.")


# SM64-specific technical content is kept as tiny tracked adapters while the
# rest of the guest stays sourced from Universal Modder.
for source_name, target in (
    ("HostBlocks.java", MAIN / "HostBlocks.java"),
    ("HostSurfaceState.java", MAIN / "HostSurfaceState.java"),
    ("sm64_surface.blockstate.json", RES / "assets" / "passthrough" / "blockstates" / "sm64_surface.json"),
    ("sm64_surface.model.json", RES / "assets" / "passthrough" / "models" / "block" / "sm64_surface.json"),
):
    source = ADAPTER / source_name
    if not source.is_file():
        raise SystemExit(f"Missing guest adapter: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())

# GTA's passthrough makes the player noPhysics because GTA owns locomotion.
# SM64 is the opposite in normal gameplay: real Minecraft collision must move
# Steve on the mirrored Mario geometry, so remove that ghost-player mixin.
common_mixins = RES / "passthrough.mixins.json"
common_text = common_mixins.read_text(encoding="utf-8")
common_text = common_text.replace('"MobMixin", "PlayerMixin", "PortalMixin"', '"MobMixin", "PortalMixin"')
common_mixins.write_text(common_text, encoding="utf-8")

# Register the technical SM64 surface block during the real Fabric mod's
# normal common initialization.
passthrough_main = MAIN / "Passthrough.java"
replace_once(
    passthrough_main,
    '\tpublic void onInitialize() {\n',
    '\tpublic void onInitialize() {\n'
    '\t\tHostBlocks.initialize();\n',
)

# Let the host switch between isolated SM64 level/area build zones.
host_link = CLIENT / "HostLink.java"
replace_once(
    host_link,
    '\t\t\t\tcase "cmd" -> WorldBridge.command(m.get("c").getAsString());\n',
    '\t\t\t\tcase "cmd" -> WorldBridge.command(m.get("c").getAsString());\n'
    '\t\t\t\tcase "healthdelta" -> WorldBridge.healthDelta(m.get("d").getAsFloat());\n',
)
replace_once(
    host_link,
    '\t\t\t\tcase "ground" -> WorldBridge.solid(ints(m.getAsJsonArray("c")));\n',
    '\t\t\t\tcase "ground" -> WorldBridge.solid(ints(m.getAsJsonArray("c")));\n'
    '\t\t\t\tcase "ground16" -> WorldBridge.surface16(ints(m.getAsJsonArray("c")));\n'
    '\t\t\t\tcase "water" -> WorldBridge.water(ints(m.getAsJsonArray("c")));\n'
    '\t\t\t\tcase "surfacebegin" -> WorldBridge.beginSurfaceSnapshot();\n'
    '\t\t\t\tcase "surfaceend" -> WorldBridge.endSurfaceSnapshot();\n'
    '\t\t\t\tcase "surfacectx" -> WorldBridge.context(m.get("k").getAsString());\n',
)

# Upgrade Universal Modder's temporary barrier collision into a real,
# targetable, breakable Minecraft host-surface block.  Broken SM64 cells are
# persisted so repeated ground packets cannot recreate them.
world_bridge = MAIN / "WorldBridge.java"
replace_once(
    world_bridge,
    'import java.util.LinkedHashMap;\n',
    'import java.util.HashSet;\nimport java.util.LinkedHashMap;\n',
)
replace_once(
    world_bridge,
    'private static final Set<BlockPos> barriers = ConcurrentHashMap.newKeySet();',
    'private static final Set<BlockPos> hostSurfaces = ConcurrentHashMap.newKeySet();\n'
    '\t/** Desired host cells while a fresh SM64 collision snapshot is being installed. */\n'
    '\tprivate static Set<BlockPos> desiredHostSurfaces;\n'
    '\t/** Real Minecraft water cells mirrored from SM64 water boxes. */\n'
    '\tprivate static final Set<BlockPos> hostWater = ConcurrentHashMap.newKeySet();\n'
    '\tprivate static Set<BlockPos> desiredHostWater;',
)
replace_once(
    world_bridge,
    '\t\tbarriers.clear();\n',
    '\t\thostSurfaces.clear();\n',
)
replace_once(
    world_bridge,
    '\tstatic void detach() {\n'
    '\t\tserver = null;\n'
    '\t\thostSurfaces.clear();\n'
    '\t}\n',
    '\tstatic void detach() {\n'
    '\t\tserver = null;\n'
    '\t\thostSurfaces.clear();\n'
    '\t\thostWater.clear();\n'
    '\t\tdesiredHostSurfaces = null;\n'
    '\t\tdesiredHostWater = null;\n'
    '\t}\n',
)
replace_once(
    world_bridge,
    '\t\t\tBlockState barrier = Blocks.BARRIER.defaultBlockState();\n',
    '\t\t\tBlockState surface = HostBlocks.SM64_SURFACE.defaultBlockState();\n',
)
replace_once(
    world_bridge,
    '\t\t\t\t\tif (level.isInWorldBounds(pos) && level.getBlockState(pos).isAir()) {\n'
    '\t\t\t\t\t\tlevel.setBlock(pos, barrier, Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t\t\tbarriers.add(pos.immutable());\n',
    '\t\t\t\t\tif (level.isInWorldBounds(pos) && !HostSurfaceState.mined(pos)) {\n'
    '\t\t\t\t\t\tBlockPos immutable = pos.immutable();\n'
    '\t\t\t\t\t\tBlockState current = level.getBlockState(pos);\n'
    '\t\t\t\t\t\tif (current.isAir()) {\n'
    '\t\t\t\t\t\t\tlevel.setBlock(pos, surface, Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t\t\t\tcurrent = surface;\n'
    '\t\t\t\t\t\t}\n'
    '\t\t\t\t\t\tif (current.is(HostBlocks.SM64_SURFACE)) {\n'
    '\t\t\t\t\t\t\thostSurfaces.add(immutable);\n'
    '\t\t\t\t\t\t\tif (desiredHostSurfaces != null) desiredHostSurfaces.add(immutable);\n'
    '\t\t\t\t\t\t}\n',
)
# Precise SM64 floor packets use {x,z,blockY,height16}. Three full
# support cells are installed below the partial top cell, while the top shape
# follows the original polygon height to 1/16 block.
replace_once(
    world_bridge,
    '\t/** Remove every barrier we placed (e.g. when the host teleports somewhere else). */\n',
    '\t/** Precise SM64 floor cells: {x,z,y,height16,...}. */\n'
    '\tpublic static void surface16(final int[] cells) {\n'
    '\t\tMinecraftServer s = server;\n'
    '\t\tif (s == null) return;\n'
    '\t\ts.execute(() -> {\n'
    '\t\t\tServerLevel level = s.overworld();\n'
    '\t\t\tBlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();\n'
    '\t\t\tplacingGround = true;\n'
    '\t\t\tfor (int i = 0; i + 3 < cells.length; i += 4) {\n'
    '\t\t\t\tint x = cells[i];\n'
    '\t\t\t\tint z = cells[i + 1];\n'
    '\t\t\t\tint topY = cells[i + 2];\n'
    '\t\t\t\tint height = Math.clamp(cells[i + 3], 1, 16);\n'
    '\t\t\t\tfor (int y = topY - 3; y <= topY; ++y) {\n'
    '\t\t\t\t\tpos.set(x, y, z);\n'
    '\t\t\t\t\tif (!level.isInWorldBounds(pos) || HostSurfaceState.mined(pos)) continue;\n'
    '\t\t\t\t\tBlockPos immutable = pos.immutable();\n'
    '\t\t\t\t\tint h = y == topY ? height : 16;\n'
    '\t\t\t\t\tBlockState wanted = HostBlocks.SM64_SURFACE.defaultBlockState()\n'
    '\t\t\t\t\t\t.setValue(HostBlocks.Sm64SurfaceBlock.HEIGHT, h);\n'
    '\t\t\t\t\tBlockState current = level.getBlockState(pos);\n'
    '\t\t\t\t\tif (current.isAir() || current.is(HostBlocks.SM64_SURFACE)) {\n'
    '\t\t\t\t\t\tif (!current.equals(wanted)) {\n'
    '\t\t\t\t\t\t\tlevel.setBlock(pos, wanted, Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t\t\t}\n'
    '\t\t\t\t\t\thostSurfaces.add(immutable);\n'
    '\t\t\t\t\t\tif (desiredHostSurfaces != null) desiredHostSurfaces.add(immutable);\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t}\n'
    '\t\t\t}\n'
    '\t\t\tplacingGround = false;\n'
    '\t\t});\n'
    '\t}\n\n'
    '\t/** Remove every barrier we placed (e.g. when the host teleports somewhere else). */\n',
)

replace_once(
    world_bridge,
    '\t\t\tfor (BlockPos pos : barriers) {\n'
    '\t\t\t\tif (level.getBlockState(pos).is(Blocks.BARRIER)) {\n',
    '\t\t\tfor (BlockPos pos : hostSurfaces) {\n'
    '\t\t\t\tif (level.getBlockState(pos).is(HostBlocks.SM64_SURFACE)) {\n',
)
replace_once(
    world_bridge,
    '\t\t\tbarriers.clear();\n',
    '\t\t\thostSurfaces.clear();\n',
)
replace_once(
    world_bridge,
    '\t\treturn !state.isAir() && !state.is(Blocks.BARRIER) && !state.getCollisionShape(level, pos).isEmpty() && !Nether.isGround(pos);',
    '\t\treturn !state.isAir() && !state.is(Blocks.BARRIER) && !state.is(HostBlocks.SM64_SURFACE)\n'
    '\t\t\t&& !state.getCollisionShape(level, pos).isEmpty() && !Nether.isGround(pos);',
)

replace_once(
    world_bridge,
    '\t/** Run a command as the server (op). Results go to the log, not to chat (send_command_feedback is off). */\n'
    '\tpublic static void command(final String command) {\n',
    '\t/** Mirror SM64 water volumes as actual Minecraft source-water blocks. */\n'
    '\tpublic static void water(final int[] columns) {\n'
    '\t\tMinecraftServer s = server;\n'
    '\t\tif (s == null) return;\n'
    '\t\ts.execute(() -> {\n'
    '\t\t\tServerLevel level = s.overworld();\n'
    '\t\t\tBlockState water = Blocks.WATER.defaultBlockState();\n'
    '\t\t\tBlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();\n'
    '\t\t\tplacingGround = true;\n'
    '\t\t\tfor (int i = 0; i + 3 < columns.length; i += 4) {\n'
    '\t\t\t\tfor (int y = columns[i + 2]; y <= columns[i + 3]; y++) {\n'
    '\t\t\t\t\tpos.set(columns[i], y, columns[i + 1]);\n'
    '\t\t\t\t\tif (!level.isInWorldBounds(pos)) continue;\n'
    '\t\t\t\t\tBlockPos immutable = pos.immutable();\n'
    '\t\t\t\t\tBlockState current = level.getBlockState(pos);\n'
    '\t\t\t\t\tif (current.isAir()) {\n'
    '\t\t\t\t\t\tlevel.setBlock(pos, water, Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t\t\thostWater.add(immutable);\n'
    '\t\t\t\t\t\tif (desiredHostWater != null) desiredHostWater.add(immutable);\n'
    '\t\t\t\t\t} else if (hostWater.contains(immutable) && current.is(Blocks.WATER)) {\n'
    '\t\t\t\t\t\tif (desiredHostWater != null) desiredHostWater.add(immutable);\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t}\n'
    '\t\t\t}\n'
    '\t\t\tplacingGround = false;\n'
    '\t\t});\n'
    '\t}\n\n'
    '\t/** Begin an atomic-ish host collision refresh. Executor ordering keeps begin/ground/end ordered. */\n'
    '\tpublic static void beginSurfaceSnapshot() {\n'
    '\t\tMinecraftServer s = server;\n'
    '\t\tif (s == null) return;\n'
    '\t\ts.execute(() -> {\n'
    '\t\t\tdesiredHostSurfaces = new HashSet<>();\n'
    '\t\t\tdesiredHostWater = new HashSet<>();\n'
    '\t\t});\n'
    '\t}\n\n'
    '\t/** Remove stale streamed cells only after the complete fresh snapshot has arrived. */\n'
    '\tpublic static void endSurfaceSnapshot() {\n'
    '\t\tMinecraftServer s = server;\n'
    '\t\tif (s == null) return;\n'
    '\t\ts.execute(() -> {\n'
    '\t\t\tif (desiredHostSurfaces == null) return;\n'
    '\t\t\tServerLevel level = s.overworld();\n'
    '\t\t\tplacingGround = true;\n'
    '\t\t\tfor (BlockPos pos : new HashSet<>(hostSurfaces)) {\n'
    '\t\t\t\tif (!desiredHostSurfaces.contains(pos)) {\n'
    '\t\t\t\t\tif (level.getBlockState(pos).is(HostBlocks.SM64_SURFACE)) {\n'
    '\t\t\t\t\t\tlevel.setBlock(pos, Blocks.AIR.defaultBlockState(), Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t\thostSurfaces.remove(pos);\n'
    '\t\t\t\t}\n'
    '\t\t\t}\n'
    '\t\t\tfor (BlockPos pos : new HashSet<>(hostWater)) {\n'
    '\t\t\t\tif (desiredHostWater == null || !desiredHostWater.contains(pos)) {\n'
    '\t\t\t\t\tif (level.getBlockState(pos).is(Blocks.WATER)) {\n'
    '\t\t\t\t\t\tlevel.setBlock(pos, Blocks.AIR.defaultBlockState(), Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t\thostWater.remove(pos);\n'
    '\t\t\t\t}\n'
    '\t\t\t}\n'
    '\t\t\tplacingGround = false;\n'
    '\t\t\tdesiredHostSurfaces = null;\n'
    '\t\t\tdesiredHostWater = null;\n'
    '\t\t});\n'
    '\t}\n\n'
    "\t/** Switch the persistent SM64 terrain-edit context and remove the previous level's streamed surface cells. */\n"
    '\tpublic static void context(final String key) {\n'
    '\t\tMinecraftServer s = server;\n'
    '\t\tif (s == null) {\n'
    '\t\t\tHostSurfaceState.setContext(key);\n'
    '\t\t\treturn;\n'
    '\t\t}\n\n'
    '\t\ts.execute(() -> {\n'
    '\t\t\tServerLevel level = s.overworld();\n'
    '\t\t\tplacingGround = true;\n'
    '\t\t\tfor (BlockPos pos : hostSurfaces) {\n'
    '\t\t\t\tif (level.getBlockState(pos).is(HostBlocks.SM64_SURFACE)) {\n'
    '\t\t\t\t\tlevel.setBlock(pos, Blocks.AIR.defaultBlockState(), Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t}\n'
    '\t\t\t}\n'
    '\t\t\tfor (BlockPos pos : hostWater) {\n'
    '\t\t\t\tif (level.getBlockState(pos).is(Blocks.WATER)) {\n'
    '\t\t\t\t\tlevel.setBlock(pos, Blocks.AIR.defaultBlockState(), Block.UPDATE_CLIENTS | Block.UPDATE_KNOWN_SHAPE);\n'
    '\t\t\t\t}\n'
    '\t\t\t}\n'
    '\t\t\tplacingGround = false;\n'
    '\t\t\thostSurfaces.clear();\n'
    '\t\t\thostWater.clear();\n'
    '\t\t\tdesiredHostSurfaces = null;\n'
    '\t\t\tdesiredHostWater = null;\n'
    '\t\t\tHostSurfaceState.setContext(key);\n'
    '\t\t});\n'
    '\t}\n\n'
    '\t/** Apply native SM64 damage/healing to the real Minecraft survival health bar. */\n'
    '\tpublic static void healthDelta(final float delta) {\n'
    '\t\tMinecraftServer s = server;\n'
    '\t\tif (s == null) return;\n'
    '\t\ts.execute(() -> {\n'
    '\t\t\tif (s.getPlayerList().getPlayers().isEmpty()) return;\n'
    '\t\t\tServerPlayer player = s.getPlayerList().getPlayers().get(0);\n'
    '\t\t\tplayer.setHealth(Math.clamp(player.getHealth() + delta, 0.0F, player.getMaxHealth()));\n'
    '\t\t});\n'
    '\t}\n\n'
    '\t/** Run a command as the server (op). Results go to the log, not to chat (send_command_feedback is off). */\n'
    '\tpublic static void command(final String command) {\n',
)

replace_once(
    world_bridge,
    '\t\tNether.onBlockChanged(pos, state);\n'
    '\t\tif (!placingGround) {\n',
    '\t\tNether.onBlockChanged(pos, state);\n'
    '\t\tif (!placingGround && hostSurfaces.remove(pos) && !state.is(HostBlocks.SM64_SURFACE)) {\n'
    '\t\t\tHostSurfaceState.markMined(pos);\n'
    '\t\t\tPassthrough.events.accept(String.format(Locale.ROOT,\n'
    '\t\t\t\t"{\\"t\\":\\"surfacebreak\\",\\"p\\":[%d,%d,%d]}", pos.getX(), pos.getY(), pos.getZ()));\n'
    '\t\t\treturn;\n'
    '\t\t}\n'
    '\t\tif (!placingGround) {\n',
)

# 1) Tobyn-style camera ownership: in normal SM64 gameplay Minecraft's
# *actual* first/third-person camera is the source of truth.  Do not reconstruct
# a GTA-style chase camera in the host and then force Minecraft back onto it.
camera = CLIENT / "mixin" / "CameraMixin.java"
replace_once(
    camera,
    'import dev.rehan.passthrough.client.FrameExporter;\n',
    'import dev.rehan.passthrough.Passthrough;\n'
    'import dev.rehan.passthrough.client.FrameExporter;\n'
    'import java.util.Locale;\n'
    'import net.minecraft.client.CameraType;\n',
)
replace_once(
    camera,
    '\t\tHostState.Pose p = HostState.frame();\n'
    '\t\tif (p == null) {\n'
    '\t\t\treturn;\n'
    '\t\t}\n\n'
    '\t\tthis.xRot = p.pitch();\n',
    '\t\tHostState.Pose p = HostState.frame();\n'
    '\t\tif (p == null) {\n'
    '\t\t\treturn;\n'
    '\t\t}\n\n'
    '\t\tif (p.drive()) {\n'
    '\t\t\t// Vanilla Minecraft has already positioned this camera at the tail of\n'
    '\t\t\t// alignWithEntity. Send that exact camera back to SM64, including\n'
    '\t\t\t// Minecraft third-person wall collision and first-person eye height.\n'
    '\t\t\tCamera actual = Minecraft.getInstance().gameRenderer.mainCamera();\n'
    '\t\t\tVec3 at = actual.position();\n'
    '\t\t\tboolean fp = Minecraft.getInstance().options.getCameraType() == CameraType.FIRST_PERSON;\n'
    '\t\t\tPassthrough.events.accept(String.format(Locale.ROOT,\n'
    '\t\t\t\t"{\\\"t\\\":\\\"mccam\\\",\\\"p\\\":[%.6f,%.6f,%.6f],\\\"r\\\":[%.4f,%.4f],\\\"fp\\\":%b}",\n'
    '\t\t\t\tat.x, at.y, at.z, this.yRot, this.xRot, fp));\n'
    '\t\t\treturn;\n'
    '\t\t}\n\n'
    '\t\tthis.xRot = p.pitch();\n',
)
replace_once(
    camera,
    "this.detached = !p.firstPerson() && !inside;",
    "this.detached = !p.firstPerson(); // host-follow mode only; drive mode keeps vanilla Minecraft camera",
)

# 2) Feed real Minecraft movement and mouse look from the focused SM64 window.
client_input = CLIENT / "ClientInput.java"
replace_once(
    client_input,
    'import net.minecraft.client.Minecraft;\n',
    'import net.minecraft.client.CameraType;\n'
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
    '			case "perspective" -> {\n'
    '				CameraType current = minecraft.options.getCameraType();\n'
    '				CameraType next = current == CameraType.FIRST_PERSON\n'
    '					? CameraType.THIRD_PERSON_BACK\n'
    '					: current == CameraType.THIRD_PERSON_BACK\n'
    '						? CameraType.THIRD_PERSON_FRONT\n'
    '						: CameraType.FIRST_PERSON;\n'
    '				minecraft.options.setCameraType(next);\n'
    '			}\n'
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

# When a real Minecraft Screen is open, mouse clicks belong to the screen,
# not to gameplay attack/use mappings that could fire later after it closes.
replace_once(
    client_input,
    '			case "key" -> {\n'
    '				String k = m.get("k").getAsString();\n'
    '				boolean down = !m.has("down") || m.get("down").getAsBoolean();\n',
    '			case "key" -> {\n'
    '				String k = m.get("k").getAsString();\n'
    '				if (minecraft.gui.screen() != null\n'
    '					&& (k.equals("attack") || k.equals("use") || k.equals("pick") || k.equals("drop") || k.equals("swap"))) {\n'
    '					return;\n'
    '				}\n'
    '				boolean down = !m.has("down") || m.get("down").getAsBoolean();\n',
)

# Keep the real Minecraft render window offscreen even if Universal Modder's
# existing view handler restores it while matching the SM64 viewport.
replace_once(
    client_input,
    '				SDLVideo.SDL_SetWindowSize(handle, w, h);\n'
    '				SDLVideo.SDL_SyncWindow(handle);\n',
    '				SDLVideo.SDL_SetWindowSize(handle, w, h);\n'
    '				SDLVideo.SDL_SetWindowPosition(handle, -32000, 0);\n'
    '				SDLVideo.SDL_SyncWindow(handle);\n',
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
    '// SM64: vanilla Minecraft F5 perspective remains authoritative while drive mode is active.',
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
    'Passthrough.events.accept(String.format(Locale.ROOT, "{\\\"t\\\":\\\"mcpos\\\",\\\"pos\\\":[%.4f,%.4f,%.4f],\\\"vel\\\":[%.3f,%.3f,%.3f],\\\"r\\\":[%.3f,%.3f],\\\"health\\\":%.3f,\\\"food\\\":%d,\\\"tn\\\":%d,\\\"fly\\\":%b}",\n'
    '				at.x, at.y, at.z, vx, vy, vz, player.getYRot(), player.getXRot(), player.getHealth(), player.getFoodData().getFoodLevel(), System.nanoTime(), player.isFallFlying()));',
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

replace_once(
    passthrough_client,
    'private static boolean worldRequested;\n',
    'private static boolean worldRequested;\n'
    '\tprivate static boolean lastScreenOpen;\n',
)
replace_once(
    passthrough_client,
    '\tprivate static void tick(final Minecraft minecraft) {\n',
    '\tprivate static void tick(final Minecraft minecraft) {\n'
    '\t\tboolean screenOpen = minecraft.level != null && minecraft.gui.screen() != null;\n'
    '\t\tif (screenOpen != lastScreenOpen) {\n'
    '\t\t\tlastScreenOpen = screenOpen;\n'
    '\t\t\tPassthrough.events.accept("{\\\"t\\\":\\\"screen\\\",\\\"open\\\":" + screenOpen + "}");\n'
    '\t\t}\n',
)


# The GTA demo resets the player's inventory on every join. For a playable
# persistent SM64 world, seed a useful building/crafting kit only once per
# player save, then leave the real Minecraft inventory completely alone.
starter_replacements = {
    '"clear @a",': '"execute as @a[tag=!sm64_starter] run give @s minecraft:bread 32",',
    '"item replace entity @a hotbar.0 with minecraft:ender_pearl 16",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.0 with minecraft:oak_planks 64",',
    '"item replace entity @a hotbar.1 with minecraft:diamond_sword",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.1 with minecraft:cobblestone 64",',
    '"item replace entity @a hotbar.2 with minecraft:crossbow[enchantments={multishot:1,quick_charge:3}]",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.2 with minecraft:grass_block 64",',
    '"item replace entity @a hotbar.3 with minecraft:bow[enchantments={power:5,infinity:1}]",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.3 with minecraft:glass 64",',
    '"item replace entity @a hotbar.4 with minecraft:tnt 64",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.4 with minecraft:crafting_table 16",',
    '"item replace entity @a hotbar.5 with minecraft:flint_and_steel",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.5 with minecraft:chest 16",',
    '"item replace entity @a hotbar.6 with minecraft:creeper_spawn_egg 64",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.6 with minecraft:torch 64",',
    '"item replace entity @a hotbar.7 with minecraft:grass_block 64",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.7 with minecraft:iron_pickaxe",',
    '"item replace entity @a hotbar.8 with minecraft:firework_rocket 64",':
        '"execute as @a[tag=!sm64_starter] run item replace entity @s hotbar.8 with minecraft:iron_sword",',
    '"give @a minecraft:arrow 64",':
        '"execute as @a[tag=!sm64_starter] run give @s minecraft:iron_axe",',
    '"item replace entity @a weapon.offhand with minecraft:firework_rocket[fireworks={flight_duration:3,explosions:[{shape:\\"large_ball\\",colors:[I;16733525,16755200],has_trail:true}]}] 64"':
        '"tag @a[tag=!sm64_starter] add sm64_starter"'
}
guest_text = passthrough_client.read_text(encoding="utf-8")
for old, new in starter_replacements.items():
    if new in guest_text:
        continue
    if old not in guest_text:
        raise RuntimeError(f"Universal Modder starter marker changed: {old!r}")
    guest_text = guest_text.replace(old, new, 1)
passthrough_client.write_text(guest_text, encoding="utf-8")



# Tobyn/crossover-style compositing requires the Minecraft world transform to
# stay registered to the host frame. View bobbing or hurt tilt would move only
# Minecraft pixels and make Steve/blocks visibly slide over SM64.
game_renderer = CLIENT / "mixin" / "GameRendererMixin.java"
replace_once(
    game_renderer,
    'import com.mojang.blaze3d.pipeline.RenderTarget;\n',
    'import com.mojang.blaze3d.pipeline.RenderTarget;\n'
    'import com.mojang.blaze3d.vertex.PoseStack;\n'
    'import net.minecraft.client.renderer.state.level.CameraRenderState;\n',
)
game_renderer_text = game_renderer.read_text(encoding="utf-8")
if "passthrough$noViewBob" not in game_renderer_text:
    insert_at = game_renderer_text.rfind("\n}")
    if insert_at < 0:
        raise RuntimeError("GameRendererMixin closing brace not found")
    game_renderer_text = game_renderer_text[:insert_at] + r"""

	@Inject(
		method = "bobView(Lnet/minecraft/client/renderer/state/level/CameraRenderState;Lcom/mojang/blaze3d/vertex/PoseStack;)V",
		at = @At("HEAD"),
		cancellable = true
	)
	private void passthrough$noViewBob(final CameraRenderState cameraState, final PoseStack poseStack, final CallbackInfo ci) {
		if (Passthrough.active) {
			ci.cancel();
		}
	}

	@Inject(
		method = "bobHurt(Lnet/minecraft/client/renderer/state/level/CameraRenderState;Lcom/mojang/blaze3d/vertex/PoseStack;)V",
		at = @At("HEAD"),
		cancellable = true
	)
	private void passthrough$noHurtTilt(final CameraRenderState cameraState, final PoseStack poseStack, final CallbackInfo ci) {
		if (Passthrough.active) {
			ci.cancel();
		}
	}
""" + game_renderer_text[insert_at:]
    game_renderer.write_text(game_renderer_text, encoding="utf-8")


# 5) The guest remains Universal Modder's real Minecraft runtime; the SM64
# delta now adds persistent, mineable host surfaces and full GUI/control sync.
if not world_bridge.is_file():
    raise SystemExit("Universal Modder WorldBridge.java missing.")

print("Universal Modder guest patched for persistent interactive SM64 world surfaces.")

