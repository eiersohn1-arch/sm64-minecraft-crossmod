#!/usr/bin/env python3
"""Apply the small SM64-specific authority delta on top of Universal Modder.

The source guest is first copied verbatim by sync_um_reference.py.  This file
then adds only the pieces the SM64 host needs: vanilla movement input,
Minecraft-authoritative locomotion, a collision-ready spawn lock, and pose
feedback to the host.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "generated" / "minecraft-guest"
CLIENT = BASE / "src" / "client" / "java" / "dev" / "rehan" / "passthrough" / "client"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Universal Modder source marker changed in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if not CLIENT.is_dir():
    raise SystemExit("Run tools/sync_um_reference.py first.")

# HostState: carry authority + a host context id so level/area transitions
# can be treated as hard spawn handoffs.
host_state = CLIENT / "HostState.java"
replace_once(
    host_state,
    "boolean drive, float lookYaw, float lookPitch, boolean gun\n\t) {",
    "boolean drive, float lookYaw, float lookPitch, boolean gun, boolean minecraftAuthority, int context\n\t) {",
)
replace_once(
    host_state,
    "\t\t\tm.has(\"gun\") && m.get(\"gun\").getAsBoolean()\n\t\t);",
    "\t\t\tm.has(\"gun\") && m.get(\"gun\").getAsBoolean(),\n"
    "\t\t\tm.has(\"mc\") && m.get(\"mc\").getAsBoolean(),\n"
    "\t\t\tm.has(\"ctx\") ? m.get(\"ctx\").getAsInt() : 0\n"
    "\t\t);",
)

# Small state holder for the asynchronous host-ground install.  We deliberately
# keep a short warm-up after the first ground packet because WorldBridge.solid
# applies barriers on the integrated-server thread.
(CLIENT / "Sm64Authority.java").write_text(r'''package dev.rehan.passthrough.client;

final class Sm64Authority {
	private static volatile boolean groundSeen;

	private Sm64Authority() {
	}

	static void clearGround() {
		groundSeen = false;
	}

	static void groundReceived() {
		groundSeen = true;
	}

	static boolean groundSeen() {
		return groundSeen;
	}
}
''', encoding="utf-8")

# HostLink: make ground readiness visible to PlayerSync.
host_link = CLIENT / "HostLink.java"
replace_once(
    host_link,
    '\t\t\t\tcase "ground" -> WorldBridge.solid(ints(m.getAsJsonArray("c")));\n'
    '\t\t\t\tcase "clear" -> WorldBridge.clearSolid();',
    '\t\t\t\tcase "ground" -> {\n'
    '\t\t\t\t\tWorldBridge.solid(ints(m.getAsJsonArray("c")));\n'
    '\t\t\t\t\tSm64Authority.groundReceived();\n'
    '\t\t\t\t}\n'
    '\t\t\t\tcase "clear" -> {\n'
    '\t\t\t\t\tSm64Authority.clearGround();\n'
    '\t\t\t\t\tWorldBridge.clearSolid();\n'
    '\t\t\t\t}',
)

# ClientInput: route the visible SM64 window's vanilla movement buttons into
# Minecraft's own KeyMappings.  No custom movement maths lives here.
client_input = CLIENT / "ClientInput.java"
replace_once(
    client_input,
    '\t\t\tswitch (m.get("t").getAsString()) {\n\t\t\tcase "key" -> {',
    '\t\t\tswitch (m.get("t").getAsString()) {\n'
    '\t\t\tcase "move" -> {\n'
    '\t\t\t\tminecraft.options.keyUp.setDown(m.get("f").getAsBoolean());\n'
    '\t\t\t\tminecraft.options.keyDown.setDown(m.get("b").getAsBoolean());\n'
    '\t\t\t\tminecraft.options.keyLeft.setDown(m.get("l").getAsBoolean());\n'
    '\t\t\t\tminecraft.options.keyRight.setDown(m.get("r").getAsBoolean());\n'
    '\t\t\t\tminecraft.options.keyJump.setDown(m.get("jump").getAsBoolean());\n'
    '\t\t\t\tminecraft.options.keyShift.setDown(m.get("sneak").getAsBoolean());\n'
    '\t\t\t\tminecraft.options.keySprint.setDown(m.get("sprint").getAsBoolean());\n'
    '\t\t\t}\n'
    '\t\t\tcase "key" -> {',
)

# PlayerSync: in mc-authority mode the host camera still drives rendering, but
# the player position is no longer snapped to the host every tick.  Context
# changes get one host->guest spawn alignment, then wait for host collision.
player_sync = CLIENT / "PlayerSync.java"
replace_once(
    player_sync,
    "\tprivate static double lastX = Double.NaN, lastZ;\n",
    "\tprivate static double lastX = Double.NaN, lastZ;\n"
    "\tprivate static int authorityContext = Integer.MIN_VALUE;\n"
    "\tprivate static boolean authorityWasActive;\n"
    "\tprivate static int collisionWarmup;\n",
)

frame_marker = '''\t\tif (p.drive()) {
\t\t\t// Minecraft flies the player (elytra): it only takes where to look, and tells the host where it is
'''
frame_insert = '''\t\tif (p.minecraftAuthority()) {
\t\t\t// The SM64 camera remains the rendering oracle for this milestone.
\t\t\t// Point the Minecraft body the same way, but never overwrite position.
\t\t\tplayer.setYRot(p.yaw());
\t\t\tplayer.setXRot(p.pitch());
\t\t\tplayer.yHeadRot = p.yaw();
\t\t\tCameraType cameraType = p.firstPerson() ? CameraType.FIRST_PERSON : CameraType.THIRD_PERSON_BACK;
\t\t\tif (minecraft.options.getCameraType() != cameraType) {
\t\t\t\tminecraft.options.setCameraType(cameraType);
\t\t\t}
\t\t\treturn;
\t\t}

\t\tif (p.drive()) {
\t\t\t// Minecraft flies the player (elytra): it only takes where to look, and tells the host where it is
'''
replace_once(player_sync, frame_marker, frame_insert)

tick_marker = '''\t\tif (p == null || p.drive()) {
\t\t\treturn;
\t\t}

\t\tdouble x = p.firstPerson() ? p.x() : p.px();
'''
tick_insert = '''\t\tif (p == null || p.drive()) {
\t\t\tauthorityWasActive = false;
\t\t\treturn;
\t\t}

\t\tif (p.minecraftAuthority()) {
\t\t\tdouble spawnX = p.px();
\t\t\tdouble spawnY = p.py();
\t\t\tdouble spawnZ = p.pz();
\t\t\tboolean entering = !authorityWasActive || authorityContext != p.context();
\t\t\tif (entering) {
\t\t\t\tauthorityWasActive = true;
\t\t\t\tauthorityContext = p.context();
\t\t\t\tcollisionWarmup = 8;
\t\t\t\tplayer.setPos(spawnX, spawnY, spawnZ);
\t\t\t\tplayer.setDeltaMovement(Vec3.ZERO);
\t\t\t\tplayer.resetFallDistance();
\t\t\t}

\t\t\tif (!Sm64Authority.groundSeen() || collisionWarmup > 0) {
\t\t\t\tif (Sm64Authority.groundSeen() && collisionWarmup > 0) {
\t\t\t\t\tcollisionWarmup--;
\t\t\t\t}
\t\t\t\tplayer.setPos(spawnX, spawnY, spawnZ);
\t\t\t\tplayer.setDeltaMovement(Vec3.ZERO);
\t\t\t\tplayer.setNoGravity(true);
\t\t\t\tplayer.resetFallDistance();
\t\t\t} else {
\t\t\t\tplayer.setNoGravity(false);
\t\t\t\tAbilities abilities = player.getAbilities();
\t\t\t\tif (abilities.flying) {
\t\t\t\t\tabilities.flying = false;
\t\t\t\t\tplayer.onUpdateAbilities();
\t\t\t\t}
\t\t\t}

\t\t\tVec3 velocity = player.getDeltaMovement();
\t\t\tPassthrough.events.accept(String.format(Locale.ROOT,
\t\t\t\t"{\\\"t\\\":\\\"mcpose\\\",\\\"p\\\":[%.6f,%.6f,%.6f],\\\"v\\\":[%.5f,%.5f,%.5f],\\\"r\\\":[%.3f,%.3f],\\\"g\\\":%b}",
\t\t\t\tplayer.getX(), player.getY(), player.getZ(),
\t\t\t\tvelocity.x, velocity.y, velocity.z,
\t\t\t\tplayer.getYRot(), player.getXRot(), player.onGround()));
\t\t\treturn;
\t\t}

\t\tauthorityWasActive = false;
\t\tplayer.setNoGravity(false);
\t\tdouble x = p.firstPerson() ? p.x() : p.px();
'''
replace_once(player_sync, tick_marker, tick_insert)

print("Applied SM64 movement-authority delta to Universal Modder guest.")
