package dev.rehan.passthrough;

import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockBehaviour;

/**
 * Technical blocks used to turn host-game geometry into real Minecraft world
 * geometry.  No BlockItem is registered: this block can exist in the world,
 * collide, be targeted and be mined, but it cannot be obtained as an item.
 */
public final class HostBlocks {
	public static final ResourceKey<Block> SM64_SURFACE_KEY = ResourceKey.create(
		Registries.BLOCK,
		Identifier.fromNamespaceAndPath(Passthrough.ID, "sm64_surface")
	);

	public static final Block SM64_SURFACE = Registry.register(
		BuiltInRegistries.BLOCK,
		SM64_SURFACE_KEY,
		new Block(
			BlockBehaviour.Properties.of()
				.strength(0.8F, 3.0F)
				.noOcclusion()
				.setId(SM64_SURFACE_KEY)
		)
	);

	private HostBlocks() {
	}

	public static void initialize() {
		// Loading this class performs the static registry initialization.
	}
}
