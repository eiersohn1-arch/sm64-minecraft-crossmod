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
    private static float lastAppliedHealth = Float.NaN;
    private static double lastX;
    private static double lastZ;
    private static boolean haveLastPosition;

    private ServerPlayerSync() {
    }

    public static void tick(Minecraft client) {
        HostState.State state = HostState.latest();

        if (!state.connected() || client.player == null) {
            lastAppliedHealth = Float.NaN;
            haveLastPosition = false;
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
        float yaw = state.yaw();
        float bodyYaw = state.bodyYaw();
        float pitch = state.pitch();
        boolean sneaking = state.sneaking();
        boolean sprinting = state.sprinting();
        int hostHealth = state.health();

        double horizontalDistance = haveLastPosition
                ? Math.hypot(x - lastX, z - lastZ)
                : 0.0;
        haveLastPosition = true;
        lastX = x;
        lastZ = z;

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
            player.yBodyRot = bodyYaw;
            player.setXRot(pitch);
            player.setShiftKeyDown(sneaking);
            player.setSprinting(sprinting);

            float targetHealth = hostHealthToMinecraft(
                    hostHealth,
                    player.getMaxHealth()
            );

            if (!Float.isNaN(lastAppliedHealth)) {
                float externalDelta =
                        player.getHealth() - lastAppliedHealth;

                if (Math.abs(externalDelta) >= 0.05f) {
                    HostLink.broadcastMessage(String.format(
                            java.util.Locale.ROOT,
                            "{\"t\":\"mc_health\",\"delta\":%.4f}",
                            externalDelta
                    ));
                }
            }

            /*
             * SM64 owns final death/respawn. Keep the Minecraft player alive
             * by a tiny amount at SM64-death health so vanilla never replaces
             * the screen with its own death flow.
             */
            targetHealth = Math.max(0.01f, targetHealth);
            player.setHealth(targetHealth);
            lastAppliedHealth = targetHealth;

            /*
             * setPos does not naturally generate walking exhaustion. Restore
             * the important Minecraft survival behavior for sprint movement.
             */
            if (!player.isCreative()
                    && sprinting
                    && horizontalDistance > 0.0
                    && horizontalDistance < 8.0) {
                player.causeFoodExhaustion(
                        (float) (horizontalDistance * 0.1)
                );
            }
        });
    }

    private static float hostHealthToMinecraft(
            int hostHealth,
            float maxHealth
    ) {
        if (hostHealth < 0x100) {
            return 0.0f;
        }

        /*
         * SM64's normal live range is 0x100..0x880. Subtract the half-wedge
         * base so 0x880 maps exactly to full Minecraft health.
         */
        float fraction = (hostHealth - 0x80) / 2048.0f;
        fraction = Math.max(0.0f, Math.min(1.0f, fraction));
        return maxHealth * fraction;
    }
}
