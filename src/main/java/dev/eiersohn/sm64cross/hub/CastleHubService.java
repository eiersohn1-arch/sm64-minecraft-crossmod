package dev.eiersohn.sm64cross.hub;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.importer.CourseBuildService;
import dev.eiersohn.sm64cross.importer.CoursePlan;
import dev.eiersohn.sm64cross.importer.CourseRuntimeService;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public final class CastleHubService {
    public static final BlockPos CASTLE_ANCHOR = new BlockPos(0, 128, 0);
    public static final BlockPos BOB_ANCHOR = new BlockPos(512, 128, 0);

    private static final BlockPos CASTLE_SENTINEL =
            CASTLE_ANCHOR.offset(0, 80, 0);
    private static final BlockPos BOB_SENTINEL =
            BOB_ANCHOR.offset(0, 80, 0);

    private static final int BLOCKS_PER_TICK = 2500;
    private static final int WARP_COOLDOWN_TICKS = 35;

    private static final Map<MinecraftServer, WorldState> STATES =
            new HashMap<>();

    private CastleHubService() {
    }

    public static void register() {
        ServerPlayConnectionEvents.JOIN.register(
                (handler, sender, server) -> onJoin(handler.player, server)
        );
        ServerTickEvents.END_SERVER_TICK.register(CastleHubService::tick);
    }

    public static boolean teleportHome(ServerPlayer player) {
        MinecraftServer server = player.getServer();
        if (server == null) {
            return false;
        }

        WorldState state = STATES.get(server);
        if (state == null || !state.castleReady || state.hubPlan == null) {
            return false;
        }

        teleport(
                player,
                CASTLE_ANCHOR.offset(state.hubPlan.lobbySpawn())
        );
        setCooldown(state, player);
        return true;
    }

    public static boolean enterBob(ServerPlayer player) {
        MinecraftServer server = player.getServer();
        if (server == null) {
            return false;
        }

        WorldState state = STATES.get(server);
        if (state == null || !state.bobReady || state.bobPlan == null) {
            return false;
        }

        startBob(state, player);
        return true;
    }

    private static void onJoin(
            ServerPlayer player,
            MinecraftServer server
    ) {
        if (player.serverLevel() != server.overworld()) {
            return;
        }

        WorldState state = STATES.computeIfAbsent(
                server,
                ignored -> loadWorldState(server)
        );

        if (state.error != null) {
            player.sendSystemMessage(Component.literal(
                    "SM64 setup missing: " + state.error
            ));
            player.sendSystemMessage(Component.literal(
                    "Run setup-windows.bat in the project folder, then restart."
            ));
            return;
        }

        if (state.castleReady) {
            teleport(player, CASTLE_ANCHOR.offset(state.hubPlan.spawn()));
            setCooldown(state, player);
            player.sendSystemMessage(Component.literal(
                    "Welcome to Peach's Castle."
            ));
        } else {
            state.waitingPlayers.add(player.getUUID());
            player.sendSystemMessage(Component.literal(
                    "Building Peach's Castle from SM64 data..."
            ));
        }
    }

    private static WorldState loadWorldState(MinecraftServer server) {
        WorldState state = new WorldState(server.overworld());

        try {
            state.hubPlan = readHubPlan();
            state.bobPlan = CourseBuildService.loadPlan(
                    "bob_omb_battlefield"
            );

            state.castleReady = state.level
                    .getBlockState(CASTLE_SENTINEL)
                    .is(Blocks.STRUCTURE_VOID);

            state.bobReady = state.level
                    .getBlockState(BOB_SENTINEL)
                    .is(Blocks.STRUCTURE_VOID);

            if (state.castleReady) {
                decorateHub(state);
            }
            if (state.bobReady) {
                decorateBobReturn(state);
            }
        } catch (IOException exception) {
            state.error = exception.getMessage();
        }

        return state;
    }

    private static void tick(MinecraftServer server) {
        WorldState state = STATES.get(server);
        if (state == null || state.error != null) {
            return;
        }

        if (!state.castleReady) {
            buildCastle(state);
            return;
        }

        if (!state.bobReady) {
            buildBob(state);
        }

        tickStarDoors(state);
        tickWarps(state);
    }

    private static void buildCastle(WorldState state) {
        int placed = 0;

        while (placed < BLOCKS_PER_TICK
                && state.castleBuildIndex < state.hubPlan.blocks().size()) {
            HubPlacement placement =
                    state.hubPlan.blocks().get(state.castleBuildIndex++);

            state.level.setBlockAndUpdate(
                    CASTLE_ANCHOR.offset(
                            placement.x(),
                            placement.y(),
                            placement.z()
                    ),
                    placement.state()
            );
            placed++;
        }

        if (state.castleBuildIndex < state.hubPlan.blocks().size()) {
            return;
        }

        state.level.setBlockAndUpdate(
                CASTLE_SENTINEL,
                Blocks.STRUCTURE_VOID.defaultBlockState()
        );

        state.castleReady = true;
        decorateHub(state);

        for (UUID playerId : state.waitingPlayers) {
            ServerPlayer player = state.level.getServer()
                    .getPlayerList()
                    .getPlayer(playerId);

            if (player != null) {
                teleport(
                        player,
                        CASTLE_ANCHOR.offset(state.hubPlan.spawn())
                );
                setCooldown(state, player);
                player.sendSystemMessage(Component.literal(
                        "Peach's Castle is ready. Bob-omb Battlefield is building in the background."
                ));
            }
        }

        state.waitingPlayers.clear();
    }

    private static void buildBob(WorldState state) {
        int placed = 0;

        while (placed < BLOCKS_PER_TICK
                && state.bobBuildIndex < state.bobPlan.blocks().size()) {
            CoursePlan.Placement placement =
                    state.bobPlan.blocks().get(state.bobBuildIndex++);

            state.level.setBlockAndUpdate(
                    BOB_ANCHOR.offset(
                            placement.x(),
                            placement.y(),
                            placement.z()
                    ),
                    placement.state()
            );
            placed++;
        }

        if (state.bobBuildIndex < state.bobPlan.blocks().size()) {
            return;
        }

        state.level.setBlockAndUpdate(
                BOB_SENTINEL,
                Blocks.STRUCTURE_VOID.defaultBlockState()
        );

        state.bobReady = true;
        decorateBobReturn(state);

        for (ServerPlayer player : state.level.players()) {
            player.sendSystemMessage(Component.literal(
                    "Bob-omb Battlefield is ready. Jump into the blue painting in the castle."
            ));
        }
    }

    private static void tickWarps(WorldState state) {
        long now = state.level.getGameTime();

        for (ServerPlayer player : state.level.players()) {
            long cooldown = state.warpCooldowns.getOrDefault(
                    player.getUUID(),
                    0L
            );

            if (now < cooldown) {
                continue;
            }

            if (state.bobReady
                    && isNear(
                            player,
                            CASTLE_ANCHOR.offset(state.hubPlan.bobPainting()),
                            2.1
                    )) {
                startBob(state, player);
                continue;
            }

            if (state.bobReady
                    && isNear(player, bobReturnPos(state), 1.8)) {
                teleport(
                        player,
                        CASTLE_ANCHOR.offset(state.hubPlan.lobbySpawn())
                );
                setCooldown(state, player);
                player.sendSystemMessage(Component.literal(
                        "Returned to Peach's Castle."
                ));
                continue;
            }

            for (HubWarp warp : state.hubPlan.warps()) {
                BlockPos from = CASTLE_ANCHOR.offset(warp.from());

                if (!isNear(player, from, 1.7)) {
                    continue;
                }

                teleport(
                        player,
                        CASTLE_ANCHOR.offset(warp.to())
                );
                setCooldown(state, player);
                break;
            }
        }
    }

    private static void startBob(
            WorldState state,
            ServerPlayer player
    ) {
        CourseRuntimeService.activate(
                "bob_omb_battlefield",
                player,
                state.level,
                BOB_ANCHOR,
                state.bobPlan
        );

        teleport(
                player,
                BOB_ANCHOR.offset(state.bobPlan.spawn())
        );
        setCooldown(state, player);

        player.sendSystemMessage(Component.literal(
                "Bob-omb Battlefield — all 7 stars are playable."
        ));
    }

    private static void tickStarDoors(WorldState state) {
        long now = state.level.getGameTime();

        if (now - state.lastDoorUpdate < 20) {
            return;
        }
        state.lastDoorUpdate = now;

        int maxStars = 0;
        for (ServerPlayer player : state.level.players()) {
            maxStars = Math.max(
                    maxStars,
                    Sm64CrossMod.STAR_STORE.get(player.getUUID())
            );
        }

        for (StarDoor door : state.hubPlan.starDoors()) {
            boolean locked = maxStars < door.required();
            applyDoor(
                    state.level,
                    CASTLE_ANCHOR.offset(door.pos()),
                    locked
            );
        }
    }

    private static void decorateHub(WorldState state) {
        for (HubWarp warp : state.hubPlan.warps()) {
            BlockPos pos = CASTLE_ANCHOR.offset(warp.from());
            state.level.setBlockAndUpdate(
                    pos,
                    Blocks.LIGHT_BLUE_CONCRETE.defaultBlockState()
            );
        }

        BlockPos painting =
                CASTLE_ANCHOR.offset(state.hubPlan.bobPainting());

        for (int dx = -2; dx <= 2; dx++) {
            for (int dy = -1; dy <= 2; dy++) {
                state.level.setBlockAndUpdate(
                        painting.offset(dx, dy, 0),
                        Blocks.BLUE_WOOL.defaultBlockState()
                );
            }
        }

        state.level.setBlockAndUpdate(
                painting,
                Blocks.CYAN_CONCRETE.defaultBlockState()
        );

        tickStarDoors(state);
    }

    private static void decorateBobReturn(WorldState state) {
        BlockPos pos = bobReturnPos(state);

        for (int dx = -1; dx <= 1; dx++) {
            for (int dz = -1; dz <= 1; dz++) {
                state.level.setBlockAndUpdate(
                        pos.offset(dx, 0, dz),
                        Blocks.PURPLE_CONCRETE.defaultBlockState()
                );
            }
        }
    }

    private static BlockPos bobReturnPos(WorldState state) {
        return BOB_ANCHOR
                .offset(state.bobPlan.spawn())
                .offset(0, 0, 6);
    }

    private static void applyDoor(
            ServerLevel level,
            BlockPos center,
            boolean locked
    ) {
        for (int dx = -1; dx <= 1; dx++) {
            for (int dy = 0; dy <= 3; dy++) {
                for (int dz = -1; dz <= 1; dz++) {
                    if (dx != 0 && dz != 0) {
                        continue;
                    }

                    BlockPos pos = center.offset(dx, dy, dz);

                    if (locked) {
                        level.setBlockAndUpdate(
                                pos,
                                Blocks.IRON_BARS.defaultBlockState()
                        );
                    } else if (level.getBlockState(pos).is(Blocks.IRON_BARS)) {
                        level.setBlockAndUpdate(
                                pos,
                                Blocks.AIR.defaultBlockState()
                        );
                    }
                }
            }
        }
    }

    private static void teleport(
            ServerPlayer player,
            BlockPos pos
    ) {
        player.teleportTo(
                pos.getX() + 0.5,
                pos.getY() + 1.0,
                pos.getZ() + 0.5
        );
    }

    private static void setCooldown(
            WorldState state,
            ServerPlayer player
    ) {
        state.warpCooldowns.put(
                player.getUUID(),
                state.level.getGameTime() + WARP_COOLDOWN_TICKS
        );
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

    private static HubPlan readHubPlan() throws IOException {
        Path path = FabricLoader.getInstance()
                .getConfigDir()
                .resolve("sm64cross")
                .resolve("imported")
                .resolve("hub")
                .resolve("peachs_castle.json");

        if (!Files.isRegularFile(path)) {
            throw new IOException(
                    "Peach's Castle plan not found: " + path
            );
        }

        try (Reader reader = Files.newBufferedReader(path)) {
            JsonObject root = JsonParser.parseReader(reader).getAsJsonObject();

            if (!"sm64cross-hub-v1".equals(
                    root.get("format").getAsString()
            )) {
                throw new IOException("Unsupported castle hub plan.");
            }

            List<BlockState> palette = new ArrayList<>();
            for (JsonElement element : root.getAsJsonArray("palette")) {
                palette.add(
                        CourseBuildService.stateFor(element.getAsString())
                );
            }

            List<HubPlacement> blocks = new ArrayList<>();
            for (JsonElement element : root.getAsJsonArray("blocks")) {
                JsonArray entry = element.getAsJsonArray();
                int paletteId = entry.get(3).getAsInt();

                if (paletteId < 0 || paletteId >= palette.size()) {
                    throw new IOException(
                            "Invalid castle palette id: " + paletteId
                    );
                }

                blocks.add(new HubPlacement(
                        entry.get(0).getAsInt(),
                        entry.get(1).getAsInt(),
                        entry.get(2).getAsInt(),
                        palette.get(paletteId)
                ));
            }

            List<HubWarp> warps = new ArrayList<>();
            for (JsonElement element : root.getAsJsonArray("warps")) {
                JsonObject warp = element.getAsJsonObject();
                warps.add(new HubWarp(
                        warp.get("id").getAsString(),
                        readPos(warp.getAsJsonArray("from")),
                        readPos(warp.getAsJsonArray("to"))
                ));
            }

            List<StarDoor> starDoors = new ArrayList<>();
            for (JsonElement element : root.getAsJsonArray("starDoors")) {
                JsonObject door = element.getAsJsonObject();
                starDoors.add(new StarDoor(
                        door.get("id").getAsString(),
                        door.get("required").getAsInt(),
                        readPos(door.getAsJsonArray("pos"))
                ));
            }

            return new HubPlan(
                    List.copyOf(blocks),
                    readPos(root.getAsJsonArray("spawn")),
                    readPos(root.getAsJsonArray("lobbySpawn")),
                    readPos(root.getAsJsonArray("bobPainting")),
                    List.copyOf(warps),
                    List.copyOf(starDoors)
            );
        } catch (RuntimeException exception) {
            throw new IOException(
                    "Invalid Peach's Castle plan: " + path,
                    exception
            );
        }
    }

    private static BlockPos readPos(JsonArray values) {
        return new BlockPos(
                values.get(0).getAsInt(),
                values.get(1).getAsInt(),
                values.get(2).getAsInt()
        );
    }

    private record HubPlacement(
            int x,
            int y,
            int z,
            BlockState state
    ) {
    }

    private record HubWarp(
            String id,
            BlockPos from,
            BlockPos to
    ) {
    }

    private record StarDoor(
            String id,
            int required,
            BlockPos pos
    ) {
    }

    private record HubPlan(
            List<HubPlacement> blocks,
            BlockPos spawn,
            BlockPos lobbySpawn,
            BlockPos bobPainting,
            List<HubWarp> warps,
            List<StarDoor> starDoors
    ) {
    }

    private static final class WorldState {
        private final ServerLevel level;
        private final Set<UUID> waitingPlayers = new HashSet<>();
        private final Map<UUID, Long> warpCooldowns = new HashMap<>();

        private HubPlan hubPlan;
        private CoursePlan bobPlan;
        private String error;

        private int castleBuildIndex;
        private int bobBuildIndex;
        private boolean castleReady;
        private boolean bobReady;
        private long lastDoorUpdate = -100;

        private WorldState(ServerLevel level) {
            this.level = level;
        }
    }
}
