package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.shapes.VoxelShape;

/**
 * Mirrors nearby Minecraft collision boxes into SM64's native dynamic-surface
 * collision system. Rendering and block logic stay 100% Minecraft-side.
 */
public final class BlockCollisionPublisher {
    private static final int HORIZONTAL_RADIUS = 12;
    private static final int VERTICAL_RADIUS = 8;
    private static final int SCAN_INTERVAL_TICKS = 4;

    private static final Map<Long, BoxSnapshot> published =
            new HashMap<>();

    private static int tick;

    private BlockCollisionPublisher() {
    }

    public static void tick(Minecraft client) {
        if (!HostLink.connected()
                || client.player == null
                || client.level == null
                || !client.level.dimension().equals(
                        Sm64CrossMod.OVERLAY_LEVEL
                )) {
            if (!published.isEmpty()) {
                published.clear();
            }
            tick = 0;
            return;
        }

        if (++tick % SCAN_INTERVAL_TICKS != 0) {
            return;
        }

        BlockPos center = client.player.blockPosition();
        Set<Long> seen = new HashSet<>();

        BlockPos.MutableBlockPos cursor =
                new BlockPos.MutableBlockPos();

        for (int y = center.getY() - VERTICAL_RADIUS;
             y <= center.getY() + VERTICAL_RADIUS;
             ++y) {
            for (int z = center.getZ() - HORIZONTAL_RADIUS;
                 z <= center.getZ() + HORIZONTAL_RADIUS;
                 ++z) {
                for (int x = center.getX() - HORIZONTAL_RADIUS;
                     x <= center.getX() + HORIZONTAL_RADIUS;
                     ++x) {
                    cursor.set(x, y, z);

                    BlockState state =
                            client.level.getBlockState(cursor);
                    if (state.isAir()) {
                        continue;
                    }

                    VoxelShape shape =
                            state.getCollisionShape(
                                    client.level,
                                    cursor
                            );
                    if (shape.isEmpty()) {
                        continue;
                    }

                    int index = 0;
                    for (AABB local : shape.toAabbs()) {
                        long key = collisionKey(
                                cursor.asLong(),
                                index++
                        );

                        BoxSnapshot box = new BoxSnapshot(
                                x + local.minX,
                                y + local.minY
                                        - Sm64CrossMod.OVERLAY_ORIGIN_Y,
                                z + local.minZ,
                                x + local.maxX,
                                y + local.maxY
                                        - Sm64CrossMod.OVERLAY_ORIGIN_Y,
                                z + local.maxZ
                        );

                        seen.add(key);

                        BoxSnapshot old = published.get(key);
                        if (!box.equals(old)) {
                            publishBox(key, box);
                            published.put(key, box);
                        }
                    }
                }
            }
        }

        var iterator = published.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<Long, BoxSnapshot> entry =
                    iterator.next();

            if (!seen.contains(entry.getKey())) {
                HostLink.broadcastMessage(String.format(
                        Locale.ROOT,
                        "{\"t\":\"unbox\",\"key\":%d}",
                        entry.getKey()
                ));
                iterator.remove();
            }
        }
    }

    private static long collisionKey(long blockPos, int index) {
        return blockPos
                ^ ((long) index * 0x9E3779B97F4A7C15L);
    }

    private static void publishBox(
            long key,
            BoxSnapshot box
    ) {
        HostLink.broadcastMessage(String.format(
                Locale.ROOT,
                "{\"t\":\"box\",\"key\":%d,"
                        + "\"min\":[%.6f,%.6f,%.6f],"
                        + "\"max\":[%.6f,%.6f,%.6f]}",
                key,
                box.minX,
                box.minY,
                box.minZ,
                box.maxX,
                box.maxY,
                box.maxZ
        ));
    }

    private record BoxSnapshot(
            double minX,
            double minY,
            double minZ,
            double maxX,
            double maxY,
            double maxZ
    ) {
    }
}
