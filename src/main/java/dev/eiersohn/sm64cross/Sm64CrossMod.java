package dev.eiersohn.sm64cross;

import net.fabricmc.api.ModInitializer;
import dev.eiersohn.sm64cross.terrain.Sm64CollisionBlock;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;
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

    /**
     * Invisible dynamic collision block used only to expose native SM64
     * surfaces to Minecraft's vanilla movement/collision engine.
     */
    public static final Block SM64_COLLISION = Registry.register(
            BuiltInRegistries.BLOCK,
            ResourceLocation.fromNamespaceAndPath(
                    MOD_ID,
                    "sm64_collision"
            ),
            new Sm64CollisionBlock(
                    BlockBehaviour.Properties.of()
                            .noOcclusion()
                            .dynamicShape()
                            .noLootTable()
                            .replaceable()
                            .noTerrainParticles()
                            .strength(-1.0f, 3600000.0f)
            )
    );

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
                 * Gravity is released by ServerPlayerSync only after a fresh
                 * SM64 collision snapshot has been installed. Do not force it
                 * on here: doing so creates a short spawn/warp window where
                 * the player can fall through the still-empty overlay world.
                 */
            }
        });
    }
}
