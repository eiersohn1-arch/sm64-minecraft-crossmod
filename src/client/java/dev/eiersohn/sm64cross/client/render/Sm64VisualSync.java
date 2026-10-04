package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.bridge.HostState;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * Universal-modder style PlayerSync: SM64 owns the authoritative player pose,
 * while the real Minecraft player is kept in the empty overlay dimension so
 * vanilla inventory/block/entity systems continue to work.
 */
public final class Sm64VisualSync {
    private static double lastX;
    private static double lastY;
    private static double lastZ;
    private static boolean haveLast;

    private Sm64VisualSync() {
    }

    public static void apply(Minecraft client) {
        HostState.State state = HostState.latest();
        LocalPlayer player = client.player;

        if (!state.connected() || player == null) {
            return;
        }

        double x = state.playerX();
        double y = renderY(state.playerY());
        double z = state.playerZ();

        double dx = haveLast ? x - lastX : 0.0;
        double dy = haveLast ? y - lastY : 0.0;
        double dz = haveLast ? z - lastZ : 0.0;
        haveLast = true;
        lastX = x;
        lastY = y;
        lastZ = z;

        player.xo = player.getX();
        player.yo = player.getY();
        player.zo = player.getZ();

        player.setPos(x, y, z);
        player.setDeltaMovement(Vec3.ZERO);
        player.setNoGravity(true);

        player.yRotO = player.getYRot();
        player.yHeadRotO = player.yHeadRot;
        player.yBodyRotO = player.yBodyRot;
        player.xRotO = player.getXRot();

        /*
         * Vanilla separates aim/head rotation from body rotation. Keep that
         * separation here: SM64 movement owns the body, while the crosshair
         * camera owns Minecraft aiming, projectile launch and item use.
         */
        player.setYRot(state.yaw());
        player.setYHeadRot(state.yaw());
        player.setYBodyRot(state.bodyYaw());
        player.setXRot(state.pitch());
        player.setShiftKeyDown(state.sneaking());
        player.setSprinting(state.sprinting());

        float horizontalSpeed = (float) Math.min(
                1.0,
                Math.sqrt(dx * dx + dz * dz) * 4.5
        );
        player.walkAnimation.update(
                horizontalSpeed,
                0.45f
        );

        float healthFraction = Math.max(
                0.0f,
                Math.min(1.0f, (state.health() >> 8) / 8.0f)
        );
        player.setHealth(
                Math.max(0.01f, player.getMaxHealth() * healthFraction)
        );
        player.getFoodData().setFoodLevel(20);
        player.getFoodData().setSaturation(20.0f);
    }

    public static double renderY(double hostY) {
        return hostY + Sm64CrossMod.OVERLAY_ORIGIN_Y;
    }
}
