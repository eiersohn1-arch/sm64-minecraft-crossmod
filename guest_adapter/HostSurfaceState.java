package dev.rehan.passthrough;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;

/**
 * Persistent record of SM64 terrain cells mined by Steve.
 *
 * The host streams its nearby collision repeatedly.  Without this tombstone
 * set, a mined host-surface cell would simply be recreated by the next ground
 * packet.  State is separated by SM64 save/level/area context.
 */
public final class HostSurfaceState {
	private static final Set<BlockPos> MINED = ConcurrentHashMap.newKeySet();
	private static String context = "default";

	private HostSurfaceState() {
	}

	public static synchronized void setContext(final String raw) {
		context = sanitize(raw);
		MINED.clear();

		Path file = file();
		if (!Files.isRegularFile(file)) {
			return;
		}

		try {
			for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
				String[] parts = line.trim().split(",");
				if (parts.length != 3) {
					continue;
				}

				try {
					MINED.add(new BlockPos(
						Integer.parseInt(parts[0]),
						Integer.parseInt(parts[1]),
						Integer.parseInt(parts[2])
					));
				} catch (NumberFormatException ignored) {
				}
			}
		} catch (IOException e) {
			Passthrough.LOG.warn("could not read SM64 mined-surface state {}", file, e);
		}
	}

	public static boolean mined(final BlockPos pos) {
		return MINED.contains(pos);
	}

	public static synchronized void markMined(final BlockPos pos) {
		BlockPos immutable = pos.immutable();
		if (!MINED.add(immutable)) {
			return;
		}

		Path file = file();
		try {
			Files.createDirectories(file.getParent());
			Files.writeString(
				file,
				immutable.getX() + "," + immutable.getY() + "," + immutable.getZ() + System.lineSeparator(),
				StandardCharsets.UTF_8,
				StandardOpenOption.CREATE,
				StandardOpenOption.APPEND
			);
		} catch (IOException e) {
			Passthrough.LOG.warn("could not persist mined SM64 surface {}", immutable, e);
		}
	}

	private static Path file() {
		return FabricLoader.getInstance()
			.getGameDir()
			.resolve("sm64-surface-breaks")
			.resolve(context + ".txt");
	}

	private static String sanitize(final String raw) {
		if (raw == null || raw.isBlank()) {
			return "default";
		}
		return raw.replaceAll("[^A-Za-z0-9._-]", "_");
	}
}
