package dev.eiersohn.sm64cross;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.Level;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class Sm64CrossMod implements ModInitializer {
    public static final String MOD_ID = "sm64cross";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    /**
     * SM64 coordinates are already converted to Minecraft blocks by the
     * bridge. This vertical origin keeps every original SM64 course inside
     * vanilla's legal build range while leaving room below and above it.
     */
    public static final double OVERLAY_ORIGIN_Y = 128.0;

    public static final ResourceKey<Level> OVERLAY_LEVEL =
            ResourceKey.create(
                    Registries.DIMENSION,
                    ResourceLocation.fromNamespaceAndPath(
                            MOD_ID,
                            "sm64_overlay"
                    )
            );

    @Override
    public void onInitialize() {
        LOGGER.info(
                "SM64 × Minecraft Crossmod hybrid gameplay mode initialized."
        );

        /*
         * The integrated Minecraft server remains the authority for real
         * Minecraft blocks, inventories, block entities, redstone, crafting,
         * mobs and item stacks. Put the local player into an empty dimension
         * so vanilla terrain never leaks into the SM64 visual world.
         */
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (!server.isSingleplayer()) {
                return;
            }

            ServerLevel overlay =
                    server.getLevel(OVERLAY_LEVEL);
            if (overlay == null) {
                return;
            }

            for (ServerPlayer player
                    : server.getPlayerList().getPlayers()) {
                if (!player.level().dimension().equals(OVERLAY_LEVEL)) {
                    player.teleportTo(
                            overlay,
                            0.5,
                            OVERLAY_ORIGIN_Y,
                            0.5,
                            player.getYRot(),
                            player.getXRot()
                    );
                }

                /*
                 * SM64 supplies player physics/vertical motion. Minecraft still
                 * simulates every other entity and all block/gameplay systems.
                 */
                player.setNoGravity(true);
                player.resetFallDistance();
            }
        });
    }
}
