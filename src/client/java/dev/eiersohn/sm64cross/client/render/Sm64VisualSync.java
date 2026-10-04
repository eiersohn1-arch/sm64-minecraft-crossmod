package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.bridge.HostState;
import dev.eiersohn.sm64cross.client.bridge.Sm64TerrainProxy;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * Movement-authority handoff.
 *
 * After the initial spawn/warp handshake this class NEVER copies Mario's
 * position into Minecraft. Vanilla Minecraft movement, gravity, sprinting,
 * crouching, jumping and collision are authoritative.
 *
 * A host snap is used only when entering a new SM64 level/area/act so the
 * Minecraft player starts at the original game's intended spawn/warp point.
 */
public final class Sm64VisualSync {
    private static boolean wasConnected;
    private static int lastLevel = Integer.MIN_VALUE;
    private static int lastArea = Integer.MIN_VALUE;
    private static int lastCourse = Integer.MIN_VALUE;
    private static int lastAct = Integer.MIN_VALUE;
    private static double lockX;
    private static double lockY;
    private static double lockZ;

    private Sm64VisualSync() {
    }

    public static void apply(Minecraft client) {
        HostState.State state = HostState.latest();
        LocalPlayer player = client.player;

        if (!state.connected() || player == null) {
            if (player != null) {
                player.setNoGravity(false);
            }
            wasConnected = false;
            return;
        }

        boolean contextChanged =
                !wasConnected
                || state.level() != lastLevel
                || state.area() != lastArea
                || state.course() != lastCourse
                || state.act() != lastAct;

        if (contextChanged) {
            Sm64TerrainProxy.invalidateForContextChange();

            lockX = state.playerX();
            lockY = renderY(state.playerY());
            lockZ = state.playerZ();

            player.setPos(lockX, lockY, lockZ);
            player.setDeltaMovement(Vec3.ZERO);
            player.setNoGravity(true);
            player.resetFallDistance();

            lastLevel = state.level();
            lastArea = state.area();
            lastCourse = state.course();
            lastAct = state.act();
        }

        wasConnected = true;

        /*
         * Never let vanilla gravity run before the SM64 collision snapshot is
         * present. Without this lock the client can fall one or more blocks in
         * the short WebSocket -> server -> block-update window at every spawn
         * or warp, which is enough to miss the floor entirely.
         */
        if (!Sm64TerrainProxy.isReady()) {
            player.setPos(lockX, lockY, lockZ);
            player.setDeltaMovement(Vec3.ZERO);
            player.setNoGravity(true);
            player.resetFallDistance();
            return;
        }

        /*
         * Once the collision world is ready, Minecraft completely owns
         * locomotion and look. The host merely follows the resulting pose.
         */
        player.setNoGravity(false);
    }

    public static double renderY(double hostY) {
        return hostY + Sm64CrossMod.OVERLAY_ORIGIN_Y;
    }
}
