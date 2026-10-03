package dev.eiersohn.sm64cross.importer;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.state.BlockState;

import java.util.List;

public record CoursePlan(
        List<Placement> blocks,
        List<BlockPos> redCoins,
        List<StarObjective> objectives
) {
    public record Placement(int x, int y, int z, BlockState state) {
    }

    public record StarObjective(
            int index,
            String id,
            String kind,
            BlockPos position
    ) {
    }
}
