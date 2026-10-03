package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * Universal-modder style PlayerSync: the host owns the pose and Minecraft
 * renders Steve at that pose.
 */
public final class Sm64VisualSync {
    private static final double VOID_Y = 10_000.0;

    private Sm64VisualSync() {
    }

    public static void apply(Minecraft client) {
        HostState.State state = HostState.latest();
        LocalPlayer player = client.player;

        if (!state.connected() || player == null) {
            return;
        }

        // Host coordinates are already Minecraft-scale. A large constant
        // vertical render origin keeps vanilla terrain away from the camera.
        player.setPos(
                state.playerX(),
                state.playerY() + VOID_Y,
                state.playerZ()
        );
        player.setDeltaMovement(Vec3.ZERO);
        player.setNoGravity(true);

        player.setYRot(state.bodyYaw());
        player.setYHeadRot(state.bodyYaw());
        player.setYBodyRot(state.bodyYaw());
        player.setXRot(0.0f);

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
        return hostY + VOID_Y;
    }
}
