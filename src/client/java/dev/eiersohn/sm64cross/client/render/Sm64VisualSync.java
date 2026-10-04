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
    private Sm64VisualSync() {
    }

    public static void apply(Minecraft client) {
        HostState.State state = HostState.latest();
        LocalPlayer player = client.player;

        if (!state.connected() || player == null) {
            return;
        }

        player.setPos(
                state.playerX(),
                renderY(state.playerY()),
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
        return hostY + Sm64CrossMod.OVERLAY_ORIGIN_Y;
    }
}
