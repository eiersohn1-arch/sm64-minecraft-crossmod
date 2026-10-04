package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import net.minecraft.client.Minecraft;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;

/**
 * Keeps only cross-engine transitions and health synchronized.
 *
 * Position is NOT forced every tick anymore. Once a level/area/act spawn is
 * aligned, the integrated Minecraft server and vanilla movement packets own
 * player locomotion completely.
 */
public final class ServerPlayerSync {
    private static float lastAppliedHealth = Float.NaN;
    private static boolean wasConnected;
    private static int lastLevel = Integer.MIN_VALUE;
    private static int lastArea = Integer.MIN_VALUE;
    private static int lastCourse = Integer.MIN_VALUE;
    private static int lastAct = Integer.MIN_VALUE;

    private ServerPlayerSync() {
    }

    public static void tick(Minecraft client) {
        HostState.State state = HostState.latest();

        if (!state.connected() || client.player == null) {
            lastAppliedHealth = Float.NaN;
            wasConnected = false;
            return;
        }

        MinecraftServer server = client.getSingleplayerServer();
        if (server == null) {
            return;
        }

        var uuid = client.player.getUUID();

        boolean contextChanged =
                !wasConnected
                || state.level() != lastLevel
                || state.area() != lastArea
                || state.course() != lastCourse
                || state.act() != lastAct;

        if (contextChanged) {
            lastLevel = state.level();
            lastArea = state.area();
            lastCourse = state.course();
            lastAct = state.act();
        }
        wasConnected = true;

        final boolean doSpawnSync = contextChanged;
        final double spawnX = state.playerX();
        final double spawnY =
                Sm64CrossMod.OVERLAY_ORIGIN_Y + state.playerY();
        final double spawnZ = state.playerZ();
        final float yaw = state.yaw();
        final float pitch = state.pitch();
        final int hostHealth = state.health();

        server.execute(() -> {
            ServerPlayer player =
                    server.getPlayerList().getPlayer(uuid);

            if (player == null
                    || !player.level().dimension().equals(
                            Sm64CrossMod.OVERLAY_LEVEL
                    )) {
                return;
            }

            if (doSpawnSync) {
                player.teleportTo(
                        player.serverLevel(),
                        spawnX,
                        spawnY,
                        spawnZ,
                        yaw,
                        pitch
                );
                player.setNoGravity(false);
                player.resetFallDistance();
            }

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

            targetHealth = Math.max(0.01f, targetHealth);
            player.setHealth(targetHealth);
            lastAppliedHealth = targetHealth;
        });
    }

    private static float hostHealthToMinecraft(
            int hostHealth,
            float maxHealth
    ) {
        if (hostHealth < 0x100) {
            return 0.0f;
        }

        float fraction = (hostHealth - 0x80) / 2048.0f;
        fraction = Math.max(0.0f, Math.min(1.0f, fraction));
        return maxHealth * fraction;
    }
}
