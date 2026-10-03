package dev.eiersohn.sm64cross.importer;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.UUID;

public final class CourseBuildService {
    private static final int BLOCKS_PER_TICK = 1800;
    private static final Deque<BuildJob> JOBS = new ArrayDeque<>();

    private CourseBuildService() {
    }

    public static void register() {
        ServerTickEvents.END_SERVER_TICK.register(server -> tick());
    }

    public static int start(ServerPlayer player, String courseId) throws IOException {
        CoursePlan plan = loadPlan(courseId);
        BlockPos anchor = player.blockPosition().below();

        JOBS.addLast(new BuildJob(
                courseId,
                player.getUUID(),
                player.serverLevel(),
                anchor,
                plan,
                true
        ));

        player.sendSystemMessage(Component.literal(
                "Building " + courseId + ": " + plan.blocks().size()
                        + " terrain blocks."
        ));

        return plan.blocks().size();
    }

    public static CoursePlan loadPlan(String courseId) throws IOException {
        if (!courseId.matches("[a-z0-9_]+")) {
            throw new IOException("Invalid course id: " + courseId);
        }

        Path path = FabricLoader.getInstance()
                .getConfigDir()
                .resolve("sm64cross")
                .resolve("imported")
                .resolve("courses")
                .resolve(courseId + ".json");

        if (!Files.isRegularFile(path)) {
            throw new IOException(
                    "Course plan not found: " + path
                            + " | Run setup-windows.bat first."
            );
        }

        return readPlan(path);
    }

    public static String status() {
        BuildJob job = JOBS.peekFirst();
        if (job == null) {
            return "No manual SM64 course build is running.";
        }
        return "Building " + job.courseId + ": "
                + job.index + "/" + job.plan.blocks().size() + " blocks";
    }

    private static void tick() {
        BuildJob job = JOBS.peekFirst();
        if (job == null) {
            return;
        }

        int placed = 0;
        while (placed < BLOCKS_PER_TICK && job.index < job.plan.blocks().size()) {
            CoursePlan.Placement placement = job.plan.blocks().get(job.index++);
            BlockPos target = job.anchor.offset(
                    placement.x(),
                    placement.y(),
                    placement.z()
            );
            job.level.setBlockAndUpdate(target, placement.state());
            placed++;
        }

        if (job.index >= job.plan.blocks().size()) {
            JOBS.removeFirst();

            ServerPlayer player = job.level.getServer()
                    .getPlayerList()
                    .getPlayer(job.playerId);

            if (player != null && job.activateOnFinish) {
                CourseRuntimeService.activate(
                        job.courseId,
                        player,
                        job.level,
                        job.anchor,
                        job.plan
                );

                player.sendSystemMessage(Component.literal(
                        "Finished building " + job.courseId
                                + " (" + job.plan.blocks().size()
                                + " terrain blocks)."
                ));
            }
        }
    }

    public static CoursePlan readPlan(Path path) throws IOException {
        try (Reader reader = Files.newBufferedReader(path)) {
            JsonObject root = JsonParser.parseReader(reader).getAsJsonObject();

            String format = root.get("format").getAsString();
            if (!"sm64cross-blockplan-v1".equals(format)
                    && !"sm64cross-blockplan-v2".equals(format)) {
                throw new IOException("Unsupported block plan format: " + format);
            }

            List<BlockState> palette = new ArrayList<>();
            for (JsonElement element : root.getAsJsonArray("palette")) {
                palette.add(stateFor(element.getAsString()));
            }

            List<CoursePlan.Placement> placements = new ArrayList<>();
            for (JsonElement element : root.getAsJsonArray("blocks")) {
                JsonArray entry = element.getAsJsonArray();
                int x = entry.get(0).getAsInt();
                int y = entry.get(1).getAsInt();
                int z = entry.get(2).getAsInt();
                int paletteId = entry.get(3).getAsInt();

                if (paletteId < 0 || paletteId >= palette.size()) {
                    throw new IOException("Invalid palette id " + paletteId);
                }

                placements.add(new CoursePlan.Placement(
                        x, y, z, palette.get(paletteId)
                ));
            }

            BlockPos spawn = root.has("spawn")
                    ? readPos(root.getAsJsonArray("spawn"))
                    : BlockPos.ZERO;

            List<BlockPos> redCoins = readPosList(root, "redCoins");
            List<BlockPos> coinMarkers = readPosList(root, "coinMarkers");

            List<CoursePlan.StarObjective> objectives = new ArrayList<>();
            if (root.has("objectives")) {
                for (JsonElement element : root.getAsJsonArray("objectives")) {
                    JsonObject objective = element.getAsJsonObject();

                    List<BlockPos> triggers = objective.has("triggerPositions")
                            ? readPosList(objective, "triggerPositions")
                            : List.of();

                    BlockPos finish = objective.has("finishPos")
                            ? readPos(objective.getAsJsonArray("finishPos"))
                            : null;

                    objectives.add(new CoursePlan.StarObjective(
                            objective.get("index").getAsInt(),
                            objective.get("id").getAsString(),
                            objective.has("name")
                                    ? objective.get("name").getAsString()
                                    : "Star " + objective.get("index").getAsInt(),
                            objective.get("kind").getAsString(),
                            readPos(objective.getAsJsonArray("pos")),
                            List.copyOf(triggers),
                            finish
                    ));
                }
            }

            return new CoursePlan(
                    List.copyOf(placements),
                    spawn,
                    List.copyOf(redCoins),
                    List.copyOf(coinMarkers),
                    List.copyOf(objectives)
            );
        } catch (RuntimeException exception) {
            throw new IOException("Invalid SM64 course plan: " + path, exception);
        }
    }

    private static List<BlockPos> readPosList(JsonObject root, String key) {
        if (!root.has(key)) {
            return List.of();
        }

        List<BlockPos> result = new ArrayList<>();
        for (JsonElement element : root.getAsJsonArray(key)) {
            result.add(readPos(element.getAsJsonArray()));
        }
        return result;
    }

    private static BlockPos readPos(JsonArray position) {
        return new BlockPos(
                position.get(0).getAsInt(),
                position.get(1).getAsInt(),
                position.get(2).getAsInt()
        );
    }

    public static BlockState stateFor(String id) {
        return switch (id) {
            case "minecraft:grass_block" -> Blocks.GRASS_BLOCK.defaultBlockState();
            case "minecraft:packed_ice" -> Blocks.PACKED_ICE.defaultBlockState();
            case "minecraft:oak_planks" -> Blocks.OAK_PLANKS.defaultBlockState();
            case "minecraft:stone_bricks" -> Blocks.STONE_BRICKS.defaultBlockState();
            case "minecraft:mossy_stone_bricks" -> Blocks.MOSSY_STONE_BRICKS.defaultBlockState();
            case "minecraft:white_concrete" -> Blocks.WHITE_CONCRETE.defaultBlockState();
            case "minecraft:polished_diorite" -> Blocks.POLISHED_DIORITE.defaultBlockState();
            case "minecraft:stone" -> Blocks.STONE.defaultBlockState();
            default -> Blocks.STONE.defaultBlockState();
        };
    }

    private static final class BuildJob {
        private final String courseId;
        private final UUID playerId;
        private final ServerLevel level;
        private final BlockPos anchor;
        private final CoursePlan plan;
        private final boolean activateOnFinish;
        private int index;

        private BuildJob(
                String courseId,
                UUID playerId,
                ServerLevel level,
                BlockPos anchor,
                CoursePlan plan,
                boolean activateOnFinish
        ) {
            this.courseId = courseId;
            this.playerId = playerId;
            this.level = level;
            this.anchor = anchor;
            this.plan = plan;
            this.activateOnFinish = activateOnFinish;
        }
    }
}
