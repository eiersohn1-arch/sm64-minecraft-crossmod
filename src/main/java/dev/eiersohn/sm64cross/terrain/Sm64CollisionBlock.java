package dev.eiersohn.sm64cross.terrain;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.VoxelShape;

/**
 * Invisible collision-only block whose VoxelShape is supplied at runtime by
 * the SM64 host.
 *
 * Unlike the old Barrier-cell proxy, one block can contain partial-height
 * floors, thin walls and ceiling slices. The block has no outline and no
 * render model, so vanilla raycasts/item use continue to see the original
 * SM64 surface instead of an artificial Minecraft cube.
 */
public final class Sm64CollisionBlock extends Block {
    private static final Map<Long, VoxelShape> SHAPES =
            new ConcurrentHashMap<>();

    public Sm64CollisionBlock(BlockBehaviour.Properties properties) {
        super(properties);
    }

    public static void setShape(BlockPos pos, VoxelShape shape) {
        if (shape == null || shape.isEmpty()) {
            SHAPES.remove(pos.asLong());
        } else {
            SHAPES.put(pos.asLong(), shape);
        }
    }

    public static void removeShape(BlockPos pos) {
        SHAPES.remove(pos.asLong());
    }

    public static void clearShapes() {
        SHAPES.clear();
    }

    public static VoxelShape shapeAt(BlockPos pos) {
        return SHAPES.getOrDefault(pos.asLong(), Shapes.empty());
    }

    @Override
    protected VoxelShape getCollisionShape(
            BlockState state,
            BlockGetter level,
            BlockPos pos,
            CollisionContext context
    ) {
        return shapeAt(pos);
    }

    @Override
    protected VoxelShape getShape(
            BlockState state,
            BlockGetter level,
            BlockPos pos,
            CollisionContext context
    ) {
        return Shapes.empty();
    }

    @Override
    protected VoxelShape getOcclusionShape(
            BlockState state,
            BlockGetter level,
            BlockPos pos
    ) {
        return Shapes.empty();
    }

    @Override
    protected RenderShape getRenderShape(BlockState state) {
        return RenderShape.INVISIBLE;
    }
}
