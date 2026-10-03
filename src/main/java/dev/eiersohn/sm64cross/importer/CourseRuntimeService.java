package dev.eiersohn.sm64cross.importer;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.block.Blocks;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public final class CourseRuntimeService {
    private static final List<RuntimeState> ACTIVE = new ArrayList<>();

    private CourseRuntimeService() {
    }

    public static void register() {
        ServerTickEvents.END_SERVER_TICK.register(server -> tick());
    }

    public static void activate(
            String courseId,
            ServerPlayer player,
            ServerLevel level,
            BlockPos anchor,
            CoursePlan plan
    ) {
        ACTIVE.removeIf(state ->
                state.playerId.equals(player.getUUID())
                        && state.courseId.equals(courseId)
        );

        RuntimeState state = new RuntimeState(
                courseId,
                player.getUUID(),
                level,
                anchor
        );

        CoursePlan.StarObjective redCoinReward = null;

        for (CoursePlan.StarObjective objective : plan.objectives()) {
            if ("red_coins".equals(objective.kind())) {
                redCoinReward = objective;
                continue;
            }

            if ("static".equals(objective.kind())
                    && !Sm64CrossMod.STAR_STORE.has(player.getUUID(), objective.id())) {
                BlockPos absolute = anchor.offset(objective.position());
                level.setBlockAndUpdate(absolute, Blocks.GOLD_BLOCK.defaultBlockState());
                state.starMarkers.put(absolute, objective.id());
            }
        }

        if (redCoinReward != null
                && !Sm64CrossMod.STAR_STORE.has(player.getUUID(), redCoinReward.id())) {
            state.redCoinReward = redCoinReward;

            for (BlockPos relative : plan.redCoins()) {
                BlockPos absolute = anchor.offset(relative);
                level.setBlockAndUpdate(absolute, Blocks.RED_CONCRETE.defaultBlockState());
                state.redCoins.add(absolute);
            }
        }

        ACTIVE.add(state);

        player.sendSystemMessage(Component.literal(
                "SM64 mission runtime active for " + courseId
                        + ": " + state.redCoins.size() + " red coins."
        ));
    }

    private static void tick() {
        Iterator<RuntimeState> states = ACTIVE.iterator();

        while (states.hasNext()) {
            RuntimeState state = states.next();
            ServerPlayer player = state.level.getServer()
                    .getPlayerList()
                    .getPlayer(state.playerId);

            if (player == null) {
                continue;
            }

            collectRedCoins(state, player);
            collectStars(state, player);

            if (state.redCoins.isEmpty()
                    && state.starMarkers.isEmpty()
                    && state.redCoinRewardSpawned) {
                states.remove();
            }
        }
    }

    private static void collectRedCoins(RuntimeState state, ServerPlayer player) {
        Iterator<BlockPos> coins = state.redCoins.iterator();

        while (coins.hasNext()) {
            BlockPos pos = coins.next();

            if (!isNear(player, pos, 1.45)) {
                continue;
            }

            state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
            coins.remove();
            state.redCoinsCollected++;

            player.sendSystemMessage(Component.literal(
                    "Red Coin " + state.redCoinsCollected + "/8"
            ));
        }

        if (state.redCoinReward != null
                && state.redCoins.isEmpty()
                && !state.redCoinRewardSpawned) {
            state.redCoinRewardSpawned = true;

            BlockPos starPos = state.anchor.offset(state.redCoinReward.position());
            state.level.setBlockAndUpdate(
                    starPos,
                    Blocks.GOLD_BLOCK.defaultBlockState()
            );
            state.starMarkers.put(starPos, state.redCoinReward.id());

            player.sendSystemMessage(Component.literal(
                    "8 Red Coins! The Power Star appeared."
            ));
        }
    }

    private static void collectStars(RuntimeState state, ServerPlayer player) {
        Iterator<Map.Entry<BlockPos, String>> stars =
                state.starMarkers.entrySet().iterator();

        while (stars.hasNext()) {
            Map.Entry<BlockPos, String> entry = stars.next();
            BlockPos pos = entry.getKey();

            if (!isNear(player, pos, 1.6)) {
                continue;
            }

            state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
            stars.remove();

            if (Sm64CrossMod.STAR_STORE.collectUnique(
                    player.getUUID(),
                    entry.getValue()
            )) {
                int total = Sm64CrossMod.STAR_STORE.get(player.getUUID());
                player.sendSystemMessage(Component.literal(
                        "Power Star collected: " + entry.getValue()
                                + "  (" + total + "/120)"
                ));
            }
        }
    }

    private static boolean isNear(
            ServerPlayer player,
            BlockPos pos,
            double radius
    ) {
        double dx = player.getX() - (pos.getX() + 0.5);
        double dy = player.getY() - (pos.getY() + 0.5);
        double dz = player.getZ() - (pos.getZ() + 0.5);
        return dx * dx + dy * dy + dz * dz <= radius * radius;
    }

    private static final class RuntimeState {
        private final String courseId;
        private final UUID playerId;
        private final ServerLevel level;
        private final BlockPos anchor;
        private final Set<BlockPos> redCoins = new HashSet<>();
        private final Map<BlockPos, String> starMarkers = new HashMap<>();
        private CoursePlan.StarObjective redCoinReward;
        private int redCoinsCollected;
        private boolean redCoinRewardSpawned;

        private RuntimeState(
                String courseId,
                UUID playerId,
                ServerLevel level,
                BlockPos anchor
        ) {
            this.courseId = courseId;
            this.playerId = playerId;
            this.level = level;
            this.anchor = anchor;
        }
    }
}
