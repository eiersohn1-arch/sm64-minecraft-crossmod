package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.client.bridge.PassthroughBridgeClient;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * Mirrors the authoritative SM64 player into a render-only region of the
 * Minecraft world. The huge Y offset keeps normal Minecraft terrain outside
 * the SM64 camera frustum, while Steve, held items and particles can still be
 * rendered by vanilla Minecraft.
 */
public final class Sm64VisualSync {
    public static final double SM64_UNITS_PER_BLOCK = 100.0;
    public static final double VOID_Y = 10_000.0;

    private Sm64VisualSync() {
    }

    public static double x(double sm64X) {
        return sm64X / SM64_UNITS_PER_BLOCK;
    }

    public static double y(double sm64Y) {
        return VOID_Y + sm64Y / SM64_UNITS_PER_BLOCK;
    }

    public static double z(double sm64Z) {
        return -sm64Z / SM64_UNITS_PER_BLOCK;
    }

    public static void apply(Minecraft client) {
        PassthroughBridgeClient.HostState state =
                PassthroughBridgeClient.hostState();

        LocalPlayer player = client.player;
        if (player == null || !state.connected()) {
            return;
        }

        player.setPos(
                x(state.playerX()),
                y(state.playerY()),
                z(state.playerZ())
        );

        player.setDeltaMovement(Vec3.ZERO);
        player.setNoGravity(true);

        float yaw = (float) (
                -state.faceAngle() * 360.0 / 65536.0
        );
        player.setYRot(yaw);
        player.setYHeadRot(yaw);
        player.setYBodyRot(yaw);
        player.setXRot(0.0f);
    }
}
