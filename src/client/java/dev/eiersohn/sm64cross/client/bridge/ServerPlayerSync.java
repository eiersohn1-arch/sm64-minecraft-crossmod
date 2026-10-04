package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import net.minecraft.client.Minecraft;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.phys.Vec3;

/**
 * Keeps the integrated-server player at the same authoritative SM64 pose as
 * the visible client player. This makes vanilla reach checks, containers,
 * projectiles, item use, mobs and block interaction operate at the real
 * crossmod position instead of at the old hidden-world spawn point.
 */
public final class ServerPlayerSync {
    private ServerPlayerSync() {
    }

    public static void tick(Minecraft client) {
        HostState.State state = HostState.latest();

        if (!state.connected() || client.player == null) {
            return;
        }

        MinecraftServer server = client.getSingleplayerServer();
        if (server == null) {
            return;
        }

        var uuid = client.player.getUUID();
        double x = state.playerX();
        double y = Sm64CrossMod.OVERLAY_ORIGIN_Y + state.playerY();
        double z = state.playerZ();
        float yaw = state.bodyYaw();
        float pitch = state.viewMode() == 0 ? state.pitch() : 0.0f;
        boolean sneaking = state.sneaking();
        boolean sprinting = state.sprinting();

        server.execute(() -> {
            ServerPlayer player =
                    server.getPlayerList().getPlayer(uuid);

            if (player == null
                    || !player.level().dimension().equals(
                            Sm64CrossMod.OVERLAY_LEVEL
                    )) {
                return;
            }

            player.setPos(x, y, z);
            player.setDeltaMovement(Vec3.ZERO);
            player.setNoGravity(true);
            player.resetFallDistance();

            player.setYRot(yaw);
            player.setYHeadRot(yaw);
            player.setXRot(pitch);
            player.setShiftKeyDown(sneaking);
            player.setSprinting(sprinting);
        });
    }
}
