package dev.eiersohn.sm64cross.importer;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.monster.Ravager;
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
    private static final int RACE_LIMIT_TICKS = 90 * 20;

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
        Iterator<RuntimeState> existing = ACTIVE.iterator();
        while (existing.hasNext()) {
            RuntimeState state = existing.next();
            if (state.playerId.equals(player.getUUID())
                    && state.courseId.equals(courseId)) {
                cleanup(state);
                existing.remove();
            }
        }

        RuntimeState state = new RuntimeState(
                courseId,
                player.getUUID(),
                level,
                anchor
        );

        for (CoursePlan.StarObjective objective : plan.objectives()) {
            if (Sm64CrossMod.STAR_STORE.has(player.getUUID(), objective.id())) {
                continue;
            }

            switch (objective.kind()) {
                case "boss" -> setupBoss(state, objective);
                case "race" -> setupRace(state, objective);
                case "breakable_box" -> setupBreakableBox(state, objective);
                case "red_coins" -> state.redCoinReward = objective;
                case "hidden_triggers" -> setupHiddenTriggers(state, objective);
                case "chain_chomp" -> setupChainChomp(state, objective);
                case "coins_100" -> state.hundredCoinReward = objective;
                case "static" -> spawnStar(state, objective.position(), objective);
                default -> {
                }
            }
        }

        if (state.redCoinReward != null) {
            for (BlockPos relative : plan.redCoins()) {
                BlockPos absolute = anchor.offset(relative);
                level.setBlockAndUpdate(
                        absolute,
                        Blocks.RED_CONCRETE.defaultBlockState()
                );
                state.redCoins.add(absolute);
            }
        }

        if (state.hundredCoinReward != null) {
            for (BlockPos relative : plan.coinMarkers()) {
                BlockPos absolute = anchor.offset(relative);

                if (!state.redCoins.contains(absolute)) {
                    level.setBlockAndUpdate(
                            absolute,
                            Blocks.GOLD_ORE.defaultBlockState()
                    );
                    state.coinMarkers.add(absolute);
                }
            }
        }

        ACTIVE.add(state);

        player.sendSystemMessage(Component.literal(
                "Bob-omb Battlefield ready: all uncollected missions are active."
        ));
    }

    private static void setupBoss(
            RuntimeState state,
            CoursePlan.StarObjective objective
    ) {
        BlockPos pos = state.anchor.offset(objective.position());

        Ravager boss = EntityType.RAVAGER.create(state.level);
        if (boss == null) {
            state.level.setBlockAndUpdate(
                    pos,
                    Blocks.BLACK_CONCRETE.defaultBlockState()
            );
            state.bossFallback = pos;
        } else {
            boss.moveTo(
                    pos.getX() + 0.5,
                    pos.getY() + 1.0,
                    pos.getZ() + 0.5,
                    0.0F,
                    0.0F
            );
            boss.setCustomName(Component.literal("King Bob-omb"));
            boss.setCustomNameVisible(true);
            boss.setPersistenceRequired();
            state.level.addFreshEntity(boss);
            state.kingBoss = boss;
        }

        state.bossObjective = objective;
    }

    private static void setupRace(
            RuntimeState state,
            CoursePlan.StarObjective objective
    ) {
        if (objective.finishPosition() == null) {
            return;
        }

        state.raceObjective = objective;
        state.raceStart = state.anchor.offset(objective.position());
        state.raceFinish = state.anchor.offset(objective.finishPosition());

        state.level.setBlockAndUpdate(
                state.raceStart,
                Blocks.BLUE_CONCRETE.defaultBlockState()
        );
        state.level.setBlockAndUpdate(
                state.raceFinish,
                Blocks.LIME_CONCRETE.defaultBlockState()
        );
    }

    private static void setupBreakableBox(
            RuntimeState state,
            CoursePlan.StarObjective objective
    ) {
        BlockPos pos = state.anchor.offset(objective.position());
        state.level.setBlockAndUpdate(
                pos,
                Blocks.EMERALD_BLOCK.defaultBlockState()
        );
        state.breakableBoxes.put(pos, objective);
    }

    private static void setupHiddenTriggers(
            RuntimeState state,
            CoursePlan.StarObjective objective
    ) {
        state.hiddenReward = objective;

        for (BlockPos relative : objective.triggerPositions()) {
            BlockPos absolute = state.anchor.offset(relative);
            state.level.setBlockAndUpdate(
                    absolute,
                    Blocks.YELLOW_STAINED_GLASS.defaultBlockState()
            );
            state.hiddenTriggers.add(absolute);
        }
    }

    private static void setupChainChomp(
            RuntimeState state,
            CoursePlan.StarObjective objective
    ) {
        if (objective.triggerPositions().isEmpty()) {
            spawnStar(state, objective.position(), objective);
            return;
        }

        state.chainReward = objective;
        state.chainStake = state.anchor.offset(objective.triggerPositions().getFirst());

        state.level.setBlockAndUpdate(
                state.chainStake,
                Blocks.IRON_BLOCK.defaultBlockState()
        );

        BlockPos star = state.anchor.offset(objective.position());
        state.chainStarPos = star;

        for (int dx = -2; dx <= 2; dx++) {
            for (int dy = -1; dy <= 3; dy++) {
                for (int dz = -2; dz <= 2; dz++) {
                    boolean shell = Math.abs(dx) == 2
                            || Math.abs(dz) == 2
                            || dy == 3;
                    if (shell) {
                        BlockPos cage = star.offset(dx, dy, dz);
                        state.level.setBlockAndUpdate(
                                cage,
                                Blocks.IRON_BARS.defaultBlockState()
                        );
                        state.chainCage.add(cage);
                    }
                }
            }
        }
    }

    private static void tick() {
        for (RuntimeState state : ACTIVE) {
            ServerPlayer player = state.level.getServer()
                    .getPlayerList()
                    .getPlayer(state.playerId);

            if (player == null) {
                continue;
            }

            tickBoss(state, player);
            tickRace(state, player);
            tickBreakableBoxes(state, player);
            tickRedCoins(state, player);
            tickHiddenTriggers(state, player);
            tickChainChomp(state, player);
            tickNormalCoins(state, player);
            collectStars(state, player);
        }
    }

    private static void tickBoss(RuntimeState state, ServerPlayer player) {
        if (state.bossObjective == null || state.bossRewardSpawned) {
            return;
        }

        boolean defeated = false;

        if (state.kingBoss != null) {
            defeated = !state.kingBoss.isAlive();
        } else if (state.bossFallback != null) {
            defeated = state.level.getBlockState(state.bossFallback).isAir();
        }

        if (defeated) {
            state.bossRewardSpawned = true;
            spawnStar(
                    state,
                    state.bossObjective.position(),
                    state.bossObjective
            );
            player.sendSystemMessage(Component.literal(
                    "King Bob-omb defeated! Power Star appeared."
            ));
        }
    }

    private static void tickRace(RuntimeState state, ServerPlayer player) {
        if (state.raceObjective == null || state.raceComplete) {
            return;
        }

        long now = state.level.getGameTime();

        if (state.raceStartTick < 0 && isNear(player, state.raceStart, 1.8)) {
            state.raceStartTick = now;
            player.sendSystemMessage(Component.literal(
                    "Koopa race started! Reach the green finish within 90 seconds."
            ));
            return;
        }

        if (state.raceStartTick >= 0 && isNear(player, state.raceFinish, 2.0)) {
            long elapsed = now - state.raceStartTick;

            if (elapsed <= RACE_LIMIT_TICKS) {
                state.raceComplete = true;
                spawnStar(
                        state,
                        state.raceObjective.finishPosition(),
                        state.raceObjective
                );
                player.sendSystemMessage(Component.literal(
                        "Koopa race won in " + (elapsed / 20.0) + " seconds!"
                ));
            } else {
                state.raceStartTick = -1;
                player.sendSystemMessage(Component.literal(
                        "Too slow. Touch the blue start block to retry."
                ));
            }
        }
    }

    private static void tickBreakableBoxes(
            RuntimeState state,
            ServerPlayer player
    ) {
        Iterator<Map.Entry<BlockPos, CoursePlan.StarObjective>> iterator =
                state.breakableBoxes.entrySet().iterator();

        while (iterator.hasNext()) {
            Map.Entry<BlockPos, CoursePlan.StarObjective> entry = iterator.next();

            if (!state.level.getBlockState(entry.getKey()).isAir()) {
                continue;
            }

            CoursePlan.StarObjective objective = entry.getValue();
            spawnStar(state, objective.position(), objective);
            iterator.remove();

            player.sendSystemMessage(Component.literal(
                    objective.name() + ": box broken, Power Star appeared."
            ));
        }
    }

    private static void tickRedCoins(RuntimeState state, ServerPlayer player) {
        Iterator<BlockPos> coins = state.redCoins.iterator();

        while (coins.hasNext()) {
            BlockPos pos = coins.next();

            if (!isNear(player, pos, 1.45)) {
                continue;
            }

            state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
            coins.remove();
            state.redCoinsCollected++;
            state.coinCount += 2;

            player.sendSystemMessage(Component.literal(
                    "Red Coin " + state.redCoinsCollected + "/8"
                            + " | Course coins: " + state.coinCount
            ));
        }

        if (state.redCoinReward != null
                && state.redCoins.isEmpty()
                && !state.redCoinRewardSpawned) {
            state.redCoinRewardSpawned = true;
            spawnStar(
                    state,
                    state.redCoinReward.position(),
                    state.redCoinReward
            );
            player.sendSystemMessage(Component.literal(
                    "8 Red Coins! The Power Star appeared."
            ));
        }
    }

    private static void tickHiddenTriggers(
            RuntimeState state,
            ServerPlayer player
    ) {
        if (state.hiddenReward == null || state.hiddenRewardSpawned) {
            return;
        }

        Iterator<BlockPos> triggers = state.hiddenTriggers.iterator();

        while (triggers.hasNext()) {
            BlockPos pos = triggers.next();

            if (!isNear(player, pos, 1.6)) {
                continue;
            }

            state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
            triggers.remove();
            state.hiddenTriggersCollected++;

            player.sendSystemMessage(Component.literal(
                    "Sky Ring " + state.hiddenTriggersCollected + "/5"
            ));
        }

        if (state.hiddenTriggers.isEmpty()) {
            state.hiddenRewardSpawned = true;
            spawnStar(
                    state,
                    state.hiddenReward.position(),
                    state.hiddenReward
            );
            player.sendSystemMessage(Component.literal(
                    "All 5 sky rings! Power Star appeared."
            ));
        }
    }

    private static void tickChainChomp(
            RuntimeState state,
            ServerPlayer player
    ) {
        if (state.chainReward == null || state.chainRewardSpawned) {
            return;
        }

        if (!state.level.getBlockState(state.chainStake).isAir()) {
            return;
        }

        state.chainRewardSpawned = true;

        for (BlockPos pos : state.chainCage) {
            if (state.level.getBlockState(pos).is(Blocks.IRON_BARS)) {
                state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
            }
        }

        spawnStar(
                state,
                state.chainReward.position(),
                state.chainReward
        );

        player.sendSystemMessage(Component.literal(
                "Chain Chomp's gate opened! Power Star appeared."
        ));
    }

    private static void tickNormalCoins(
            RuntimeState state,
            ServerPlayer player
    ) {
        if (state.hundredCoinReward == null
                || state.hundredCoinRewardSpawned) {
            return;
        }

        Iterator<BlockPos> coins = state.coinMarkers.iterator();

        while (coins.hasNext()) {
            BlockPos pos = coins.next();

            if (!isNear(player, pos, 1.4)) {
                continue;
            }

            if (state.level.getBlockState(pos).is(Blocks.GOLD_ORE)) {
                state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
            }

            coins.remove();
            state.coinCount++;

            if (state.coinCount % 10 == 0 || state.coinCount >= 100) {
                player.sendSystemMessage(Component.literal(
                        "Course coins: " + state.coinCount + "/100"
                ));
            }
        }

        if (state.coinCount >= 100) {
            state.hundredCoinRewardSpawned = true;
            BlockPos relative = player.blockPosition()
                    .above(2)
                    .subtract(state.anchor);

            spawnStar(
                    state,
                    relative,
                    state.hundredCoinReward
            );

            player.sendSystemMessage(Component.literal(
                    "100 Coins! Power Star appeared above you."
            ));
        }
    }

    private static void collectStars(RuntimeState state, ServerPlayer player) {
        Iterator<Map.Entry<BlockPos, CoursePlan.StarObjective>> stars =
                state.starMarkers.entrySet().iterator();

        while (stars.hasNext()) {
            Map.Entry<BlockPos, CoursePlan.StarObjective> entry = stars.next();
            BlockPos pos = entry.getKey();

            if (!isNear(player, pos, 1.6)) {
                continue;
            }

            state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
            stars.remove();

            CoursePlan.StarObjective objective = entry.getValue();

            if (Sm64CrossMod.STAR_STORE.collectUnique(
                    player.getUUID(),
                    objective.id()
            )) {
                int total = Sm64CrossMod.STAR_STORE.get(player.getUUID());
                player.sendSystemMessage(Component.literal(
                        "POWER STAR: " + objective.name()
                                + "  (" + total + "/120)"
                ));
            }
        }
    }

    private static void spawnStar(
            RuntimeState state,
            BlockPos relative,
            CoursePlan.StarObjective objective
    ) {
        if (Sm64CrossMod.STAR_STORE.has(state.playerId, objective.id())) {
            return;
        }

        BlockPos absolute = state.anchor.offset(relative);
        state.level.setBlockAndUpdate(
                absolute,
                Blocks.GOLD_BLOCK.defaultBlockState()
        );
        state.starMarkers.put(absolute, objective);
    }

    private static boolean isNear(
            ServerPlayer player,
            BlockPos pos,
            double radius
    ) {
        if (pos == null) {
            return false;
        }

        double dx = player.getX() - (pos.getX() + 0.5);
        double dy = player.getY() - (pos.getY() + 0.5);
        double dz = player.getZ() - (pos.getZ() + 0.5);
        return dx * dx + dy * dy + dz * dz <= radius * radius;
    }

    private static void cleanup(RuntimeState state) {
        if (state.kingBoss != null && state.kingBoss.isAlive()) {
            state.kingBoss.discard();
        }

        for (BlockPos pos : state.redCoins) {
            clearIf(state, pos, Blocks.RED_CONCRETE);
        }
        for (BlockPos pos : state.coinMarkers) {
            clearIf(state, pos, Blocks.GOLD_ORE);
        }
        for (BlockPos pos : state.hiddenTriggers) {
            clearIf(state, pos, Blocks.YELLOW_STAINED_GLASS);
        }
        for (BlockPos pos : state.chainCage) {
            clearIf(state, pos, Blocks.IRON_BARS);
        }
        if (state.chainStake != null) {
            clearIf(state, state.chainStake, Blocks.IRON_BLOCK);
        }
        if (state.raceStart != null) {
            clearIf(state, state.raceStart, Blocks.BLUE_CONCRETE);
        }
        if (state.raceFinish != null) {
            clearIf(state, state.raceFinish, Blocks.LIME_CONCRETE);
        }
        for (BlockPos pos : state.starMarkers.keySet()) {
            clearIf(state, pos, Blocks.GOLD_BLOCK);
        }
    }

    private static void clearIf(
            RuntimeState state,
            BlockPos pos,
            net.minecraft.world.level.block.Block block
    ) {
        if (state.level.getBlockState(pos).is(block)) {
            state.level.setBlockAndUpdate(pos, Blocks.AIR.defaultBlockState());
        }
    }

    private static final class RuntimeState {
        private final String courseId;
        private final UUID playerId;
        private final ServerLevel level;
        private final BlockPos anchor;

        private final Set<BlockPos> redCoins = new HashSet<>();
        private final Set<BlockPos> coinMarkers = new HashSet<>();
        private final Set<BlockPos> hiddenTriggers = new HashSet<>();
        private final Set<BlockPos> chainCage = new HashSet<>();

        private final Map<BlockPos, CoursePlan.StarObjective> starMarkers =
                new HashMap<>();
        private final Map<BlockPos, CoursePlan.StarObjective> breakableBoxes =
                new HashMap<>();

        private CoursePlan.StarObjective bossObjective;
        private CoursePlan.StarObjective raceObjective;
        private CoursePlan.StarObjective redCoinReward;
        private CoursePlan.StarObjective hiddenReward;
        private CoursePlan.StarObjective chainReward;
        private CoursePlan.StarObjective hundredCoinReward;

        private Ravager kingBoss;
        private BlockPos bossFallback;
        private boolean bossRewardSpawned;

        private BlockPos raceStart;
        private BlockPos raceFinish;
        private long raceStartTick = -1;
        private boolean raceComplete;

        private int redCoinsCollected;
        private boolean redCoinRewardSpawned;

        private int hiddenTriggersCollected;
        private boolean hiddenRewardSpawned;

        private BlockPos chainStake;
        private BlockPos chainStarPos;
        private boolean chainRewardSpawned;

        private int coinCount;
        private boolean hundredCoinRewardSpawned;

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
