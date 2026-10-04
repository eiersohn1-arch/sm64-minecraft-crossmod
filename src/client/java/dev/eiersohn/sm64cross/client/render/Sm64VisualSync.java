package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.bridge.HostState;
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

    private Sm64VisualSync() {
    }

    public static void apply(Minecraft client) {
        HostState.State state = HostState.latest();
        LocalPlayer player = client.player;

        if (!state.connected() || player == null) {
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
            player.setPos(
                    state.playerX(),
                    renderY(state.playerY()),
                    state.playerZ()
            );
            player.setDeltaMovement(Vec3.ZERO);
            player.resetFallDistance();

            lastLevel = state.level();
            lastArea = state.area();
            lastCourse = state.course();
            lastAct = state.act();
        }

        wasConnected = true;

        /*
         * Minecraft owns both locomotion and look rotation. Do not feed the
         * host camera back into the player every tick: the host now follows
         * the real Minecraft yaw/pitch published by InputPublisher.
         */
        player.setNoGravity(false);
    }

    public static double renderY(double hostY) {
        return hostY + Sm64CrossMod.OVERLAY_ORIGIN_Y;
    }
}
