package dev.eiersohn.sm64cross.progress;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import net.fabricmc.loader.api.FabricLoader;

import java.io.Reader;
import java.io.Writer;
import java.lang.reflect.Type;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public final class StarStore {
    private static final int MAX_STARS = 120;
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Type DATA_TYPE =
            new TypeToken<Map<String, PlayerProgress>>() {}.getType();

    private final Path path = FabricLoader.getInstance()
            .getConfigDir()
            .resolve("sm64cross")
            .resolve("stars.json");

    private final Map<String, PlayerProgress> progress = new HashMap<>();

    public synchronized void load() {
        progress.clear();
        if (!Files.exists(path)) {
            return;
        }

        try (Reader reader = Files.newBufferedReader(path)) {
            Map<String, PlayerProgress> loaded = GSON.fromJson(reader, DATA_TYPE);
            if (loaded != null) {
                loaded.forEach((key, value) -> {
                    if (value == null) {
                        return;
                    }
                    value.normalize();
                    progress.put(key, value);
                });
            }
        } catch (Exception ignored) {
            // Never stop Minecraft from starting because a local progress file is broken.
        }
    }

    public synchronized int get(UUID playerId) {
        PlayerProgress value = progress.get(playerId.toString());
        if (value == null) {
            return 0;
        }
        return clamp(value.debugStars + value.collectedStars.size());
    }

    public synchronized int add(UUID playerId, int amount) {
        PlayerProgress value = getOrCreate(playerId);
        value.debugStars = clamp(value.debugStars + amount);
        save();
        return get(playerId);
    }

    public synchronized int set(UUID playerId, int requestedTotal) {
        PlayerProgress value = getOrCreate(playerId);
        int collected = value.collectedStars.size();
        value.debugStars = Math.max(0, clamp(requestedTotal) - collected);
        save();
        return get(playerId);
    }

    public synchronized boolean collectUnique(UUID playerId, String starId) {
        PlayerProgress value = getOrCreate(playerId);

        if (value.collectedStars.contains(starId)) {
            return false;
        }

        if (get(playerId) >= MAX_STARS) {
            return false;
        }

        value.collectedStars.add(starId);
        save();
        return true;
    }

    public synchronized boolean has(UUID playerId, String starId) {
        PlayerProgress value = progress.get(playerId.toString());
        return value != null && value.collectedStars.contains(starId);
    }

    private PlayerProgress getOrCreate(UUID playerId) {
        return progress.computeIfAbsent(
                playerId.toString(),
                ignored -> new PlayerProgress()
        );
    }

    private void save() {
        try {
            Files.createDirectories(path.getParent());
            try (Writer writer = Files.newBufferedWriter(path)) {
                GSON.toJson(progress, DATA_TYPE, writer);
            }
        } catch (Exception ignored) {
            // Keep progress in memory for the running session.
        }
    }

    private static int clamp(int value) {
        return Math.max(0, Math.min(MAX_STARS, value));
    }

    private static final class PlayerProgress {
        private int debugStars;
        private Set<String> collectedStars = new HashSet<>();

        private void normalize() {
            debugStars = clamp(debugStars);
            if (collectedStars == null) {
                collectedStars = new HashSet<>();
            }
        }
    }
}
