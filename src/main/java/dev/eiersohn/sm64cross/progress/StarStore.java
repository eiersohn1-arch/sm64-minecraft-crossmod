package dev.eiersohn.sm64cross.progress;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.lang.reflect.Type;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

public final class StarStore {
    private static final int MAX_STARS = 120;
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Type DATA_TYPE = new TypeToken<Map<String, Integer>>() {}.getType();

    private final Path path = FabricLoader.getInstance()
            .getConfigDir().resolve("sm64cross").resolve("stars.json");
    private final Map<String, Integer> stars = new HashMap<>();

    public synchronized void load() {
        stars.clear();
        if (!Files.exists(path)) return;
        try (Reader reader = Files.newBufferedReader(path)) {
            Map<String, Integer> loaded = GSON.fromJson(reader, DATA_TYPE);
            if (loaded != null) {
                loaded.forEach((key, value) -> stars.put(key, clamp(value == null ? 0 : value)));
            }
        } catch (IOException ignored) {
        }
    }

    public synchronized int get(UUID playerId) {
        return stars.getOrDefault(playerId.toString(), 0);
    }

    public synchronized int add(UUID playerId, int amount) {
        return set(playerId, get(playerId) + amount);
    }

    public synchronized int set(UUID playerId, int amount) {
        int value = clamp(amount);
        stars.put(playerId.toString(), value);
        save();
        return value;
    }

    private void save() {
        try {
            Files.createDirectories(path.getParent());
            try (Writer writer = Files.newBufferedWriter(path)) {
                GSON.toJson(stars, DATA_TYPE, writer);
            }
        } catch (IOException ignored) {
        }
    }

    private static int clamp(int value) {
        return Math.max(0, Math.min(MAX_STARS, value));
    }
}
