package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import java.util.HashSet;
import java.util.Set;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.Blocks;

/**
 * Local invisible Minecraft collision shell generated from nearby native SM64
 * floor triangles. It is intentionally server-side so vanilla Minecraft mobs,
 * projectiles, dropped items and other entities collide with the SM64 ground.
 */
public final class Sm64TerrainProxy {
    private static final Set<BlockPos> active = new HashSet<>();
    private static Set<BlockPos> pending;

    private Sm64TerrainProxy() {
    }

    public static synchronized void begin() {
        pending = new HashSet<>();
    }

    public static synchronized void cell(int x, int y, int z) {
        if (pending != null) {
            pending.add(new BlockPos(x, y, z));
        }
    }

    public static synchronized void end() {
        if (pending == null) {
            return;
        }

        Set<BlockPos> desired = pending;
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
            Set<BlockPos> desired
    ) {
        ServerLevel level =
                server.getLevel(Sm64CrossMod.OVERLAY_LEVEL);

        if (level == null) {
            return;
        }

        for (BlockPos pos : Set.copyOf(active)) {
            if (!desired.contains(pos)) {
                if (level.getBlockState(pos).is(Blocks.BARRIER)) {
                    level.removeBlock(pos, false);
                }
                active.remove(pos);
            }
        }

        for (BlockPos pos : desired) {
            if (active.contains(pos)) {
                continue;
            }

            if (level.getBlockState(pos).isAir()) {
                level.setBlockAndUpdate(
                        pos,
                        Blocks.BARRIER.defaultBlockState()
                );
                active.add(pos.immutable());
            }
        }
    }

    public static synchronized void clear() {
        pending = null;

        Minecraft client = Minecraft.getInstance();
        MinecraftServer server = client.getSingleplayerServer();
        if (server == null || active.isEmpty()) {
            active.clear();
            return;
        }

        Set<BlockPos> old = Set.copyOf(active);
        active.clear();

        server.execute(() -> {
            ServerLevel level =
                    server.getLevel(Sm64CrossMod.OVERLAY_LEVEL);
            if (level == null) {
                return;
            }

            for (BlockPos pos : old) {
                if (level.getBlockState(pos).is(Blocks.BARRIER)) {
                    level.removeBlock(pos, false);
                }
            }
        });
    }
}
