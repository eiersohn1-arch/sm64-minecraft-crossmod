package dev.rehan.passthrough;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.StateDefinition;
import net.minecraft.world.level.block.state.properties.IntegerProperty;
import net.minecraft.world.phys.shapes.CollisionContext;
import net.minecraft.world.phys.shapes.VoxelShape;

/**
 * Technical blocks used to turn SM64 geometry into real Minecraft collision.
 * The host surface is invisible in the rendered world, but has a 1/16-block
 * height state so Steve can stand on Mario slopes/steps without visibly
 * sinking into or floating above the original SM64 mesh.
 */
public final class HostBlocks {
	public static final ResourceKey<Block> SM64_SURFACE_KEY = ResourceKey.create(
		Registries.BLOCK,
		Identifier.fromNamespaceAndPath(Passthrough.ID, "sm64_surface")
	);

	public static final Sm64SurfaceBlock SM64_SURFACE = Registry.register(
		BuiltInRegistries.BLOCK,
		SM64_SURFACE_KEY,
		new Sm64SurfaceBlock(
			BlockBehaviour.Properties.of()
				.strength(0.8F, 3.0F)
				.noOcclusion()
				.dynamicShape()
				.setId(SM64_SURFACE_KEY)
		)
	);

	private HostBlocks() {
	}

	public static void initialize() {
		// Loading this class performs the static registry initialization.
	}

	/**
	 * Invisible host-ground voxel. HEIGHT=1..16 controls the collision top in
	 * sixteenth-block increments, matching the strategy used by modern
	 * cross-game Minecraft bridges instead of rounding every host surface to a
	 * full cube.
	 */
	public static final class Sm64SurfaceBlock extends Block {
		public static final IntegerProperty HEIGHT = IntegerProperty.create("height", 1, 16);
		private static final VoxelShape[] SHAPES = new VoxelShape[17];

		static {
			for (int i = 1; i <= 16; ++i) {
				SHAPES[i] = Block.box(0.0, 0.0, 0.0, 16.0, i, 16.0);
			}
		}

		Sm64SurfaceBlock(final BlockBehaviour.Properties properties) {
			super(properties);
			registerDefaultState(stateDefinition.any().setValue(HEIGHT, 16));
		}

		@Override
		protected void createBlockStateDefinition(final StateDefinition.Builder<Block, BlockState> builder) {
			builder.add(HEIGHT);
		}

		@Override
		protected VoxelShape getShape(
			final BlockState state,
			final BlockGetter level,
			final BlockPos pos,
			final CollisionContext context
		) {
			return SHAPES[state.getValue(HEIGHT)];
		}

		@Override
		protected VoxelShape getCollisionShape(
			final BlockState state,
			final BlockGetter level,
			final BlockPos pos,
			final CollisionContext context
		) {
			return SHAPES[state.getValue(HEIGHT)];
		}
	}
}
