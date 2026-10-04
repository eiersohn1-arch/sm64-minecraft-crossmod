package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.terrain.Sm64CollisionBlock;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/**
 * Runtime Minecraft collision generated from the real nearby SM64 collision.
 *
 * The old implementation rounded every sample to a full Barrier block. That
 * made Minecraft movement feel like it was walking on a second voxel copy of
 * Mario's world. This version keeps Minecraft's vanilla movement engine, but
 * gives it partial-height VoxelShapes:
 *
 * - 2x2 floor samples per SM64 block cell for smoother slopes;
 * - thin wall slices positioned on the actual SM64 wall plane;
 * - exact-height ceiling slices;
 * - no render shape and no selection outline.
 *
 * Real player-created Minecraft blocks always win over proxy collision.
 */
public final class Sm64TerrainProxy {
    private static final Set<BlockPos> active = new HashSet<>();
    private static Map<BlockPos, List<Box>> pending;

    private Sm64TerrainProxy() {
    }

    public static synchronized void begin() {
        pending = new HashMap<>();
    }

    /**
     * Legacy full-cell packet support for older hosts.
     */
    public static synchronized void cell(int x, int y, int z) {
        box(x, y, z, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0);
    }

    public static synchronized void box(
            int x,
            int y,
            int z,
            double minX,
            double minY,
            double minZ,
            double maxX,
            double maxY,
            double maxZ
    ) {
        if (pending == null) {
            return;
        }

        Box box = Box.clamped(
                minX, minY, minZ,
                maxX, maxY, maxZ
        );
        if (box == null) {
            return;
        }

        pending.computeIfAbsent(
                new BlockPos(x, y, z),
                ignored -> new ArrayList<>()
        ).add(box);
    }

    public static synchronized void end() {
        if (pending == null) {
            return;
        }

        Map<BlockPos, List<Box>> desired = pending;
        pending = null;

        Minecraft client = Minecraft.getInstance();
        MinecraftServer server = client.getSingleplayerServer();

        if (server == null) {
            return;
        }

        server.execute(() -> apply(server, desired));
    }

    private static void apply(
            MinecraftServer server,
            Map<BlockPos, List<Box>> desired
    ) {
        ServerLevel level =
                server.getLevel(Sm64CrossMod.OVERLAY_LEVEL);

        if (level == null) {
            return;
        }

        for (BlockPos pos : Set.copyOf(active)) {
            if (desired.containsKey(pos)) {
                continue;
            }

            if (level.getBlockState(pos).is(
                    Sm64CrossMod.SM64_COLLISION
            )) {
                level.removeBlock(pos, false);
            }

            Sm64CollisionBlock.removeShape(pos);
            active.remove(pos);
        }

        for (Map.Entry<BlockPos, List<Box>> entry
                : desired.entrySet()) {
            BlockPos pos = entry.getKey();
            VoxelShape shape = buildShape(entry.getValue());

            if (shape.isEmpty()) {
                continue;
            }

            var state = level.getBlockState(pos);

            /*
             * Never overwrite a real Minecraft block. If the player builds
             * into a proxy cell, the real block becomes the collision source
             * and the hidden SM64 shape is discarded for this position.
             */
            if (!state.isAir()
                    && !state.is(Sm64CrossMod.SM64_COLLISION)) {
                Sm64CollisionBlock.removeShape(pos);
                active.remove(pos);
                continue;
            }

            Sm64CollisionBlock.setShape(pos, shape);

            if (!state.is(Sm64CrossMod.SM64_COLLISION)) {
                level.setBlockAndUpdate(
                        pos,
                        Sm64CrossMod.SM64_COLLISION
                                .defaultBlockState()
                );
            }

            active.add(pos.immutable());
        }
    }

    private static VoxelShape buildShape(List<Box> boxes) {
        VoxelShape result = Shapes.empty();

        for (Box box : boxes) {
            VoxelShape next = Shapes.box(
                    box.minX,
                    box.minY,
                    box.minZ,
                    box.maxX,
                    box.maxY,
                    box.maxZ
            );

            result = result.isEmpty()
                    ? next
                    : Shapes.or(result, next);
        }

        return result.optimize();
    }

    public static synchronized boolean isProxy(BlockPos pos) {
        return active.contains(pos);
    }

    public static synchronized void clear() {
        pending = null;

        Minecraft client = Minecraft.getInstance();
        MinecraftServer server = client.getSingleplayerServer();

        if (server == null || active.isEmpty()) {
            active.clear();
            Sm64CollisionBlock.clearShapes();
            return;
        }

        Set<BlockPos> old = Set.copyOf(active);
        active.clear();
        Sm64CollisionBlock.clearShapes();

        server.execute(() -> {
            ServerLevel level =
                    server.getLevel(Sm64CrossMod.OVERLAY_LEVEL);
            if (level == null) {
                return;
            }

            for (BlockPos pos : old) {
                if (level.getBlockState(pos).is(
                        Sm64CrossMod.SM64_COLLISION
                )) {
                    level.removeBlock(pos, false);
                }
            }
        });
    }

    private record Box(
            double minX,
            double minY,
            double minZ,
            double maxX,
            double maxY,
            double maxZ
    ) {
        private static Box clamped(
                double minX,
                double minY,
                double minZ,
                double maxX,
                double maxY,
                double maxZ
        ) {
            minX = clamp(minX);
            minY = clamp(minY);
            minZ = clamp(minZ);
            maxX = clamp(maxX);
            maxY = clamp(maxY);
            maxZ = clamp(maxZ);

            if (maxX - minX < 0.001
                    || maxY - minY < 0.001
                    || maxZ - minZ < 0.001) {
                return null;
            }

            return new Box(
                    minX, minY, minZ,
                    maxX, maxY, maxZ
            );
        }

        private static double clamp(double value) {
            return Math.max(0.0, Math.min(1.0, value));
        }
    }
}
