package dev.eiersohn.sm64cross.client.bridge;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

/**
 * Latest authoritative SM64 pose/state received from the host.
 *
 * The shape deliberately follows universal-modder's passthrough HostState:
 * SM64 sends camera/player state in Minecraft coordinates over WebSocket,
 * and the rendered Minecraft frame records the exact host pose it used.
 */
public final class HostState {
    private static volatile State latest = State.disconnected();

    private HostState() {
    }

    public static State latest() {
        return latest;
    }

    public static boolean connected() {
        return latest.connected();
    }

    public static void disconnect() {
        latest = State.disconnected();
    }

    public static void update(JsonObject message) {
        JsonArray camera = message.getAsJsonArray("p");
        JsonArray rotation = message.getAsJsonArray("r");
        JsonArray player = message.getAsJsonArray("pl");

        latest = new State(
                true,
                longValue(message, "f", 0L),
                number(camera, 0),
                number(camera, 1),
                number(camera, 2),
                (float) number(rotation, 0),
                (float) number(rotation, 1),
                (float) number(rotation, 2),
                (float) doubleValue(message, "fov", 45.0),
                intValue(message, "view", 1),
                number(player, 0),
                number(player, 1),
                number(player, 2),
                (float) doubleValue(message, "h", 0.0),
                intValue(message, "action", 0),
                intValue(message, "sneak", 0) != 0,
                intValue(message, "sprint", 0) != 0,
                intValue(message, "level", -1),
                intValue(message, "area", -1),
                intValue(message, "course", -1),
                intValue(message, "act", -1),
                intValue(message, "stars", 0),
                intValue(message, "health", 0),
                longValue(message, "save", 0L),
                longValue(message, "courseStars", 0L),
                intValue(message, "coins", 0),
                intValue(message, "lives", 4),
                intValue(message, "hud", 0),
                intValue(message, "timer", 0),
                longValue(message, "hitSerial", -1L),
                intValue(message, "hitCount", 0)
        );
    }

    private static double number(JsonArray array, int index) {
        return array != null && array.size() > index
                ? array.get(index).getAsDouble()
                : 0.0;
    }

    private static int intValue(JsonObject object, String key, int fallback) {
        return object.has(key) ? object.get(key).getAsInt() : fallback;
    }

    private static long longValue(JsonObject object, String key, long fallback) {
        return object.has(key) ? object.get(key).getAsLong() : fallback;
    }

    private static double doubleValue(JsonObject object, String key, double fallback) {
        return object.has(key) ? object.get(key).getAsDouble() : fallback;
    }

    public record State(
            boolean connected,
            long hostFrame,
            double cameraX,
            double cameraY,
            double cameraZ,
            float yaw,
            float pitch,
            float roll,
            float fov,
            int viewMode,
            double playerX,
            double playerY,
            double playerZ,
            float bodyYaw,
            int marioAction,
            boolean sneaking,
            boolean sprinting,
            int level,
            int area,
            int course,
            int act,
            int stars,
            int health,
            long saveFlags,
            long courseStarFlags,
            int coins,
            int lives,
            int hudFlags,
            int timerFrames,
            long lastHitAttackSerial,
            int hitCount
    ) {
        static State disconnected() {
            return new State(
                    false,
                    0L,
                    0.0, 0.0, 0.0,
                    0.0f, 0.0f, 0.0f, 45.0f,
                    1,
                    0.0, 0.0, 0.0,
                    0.0f,
                    -1, -1, -1, -1,
                    0, 0, 0L, 0L,
                    0, 4, 0, 0,
                    -1L, 0
            );
        }
    }
}
