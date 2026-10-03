package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.Sm64Keys;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ItemStack;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public final class PassthroughBridgeClient {
    private static final int HOST_PORT = 6464;
    private static final int MAX_PACKET = 2048;

    private static DatagramSocket socket;
    private static long sequence;
    private static long attackSerial;
    private static boolean previousAttackDown;
    private static boolean hostSeen;
    private static HostState hostState = HostState.disconnected();

    private PassthroughBridgeClient() {
    }

    public static void start() {
        if (socket != null) {
            return;
        }

        try {
            socket = new DatagramSocket();
            socket.connect(InetAddress.getLoopbackAddress(), HOST_PORT);
            socket.setSoTimeout(1);

            Sm64CrossMod.LOGGER.info(
                    "Crossmod bridge ready on localhost UDP port {}.",
                    HOST_PORT
            );
        } catch (IOException exception) {
            Sm64CrossMod.LOGGER.error(
                    "Could not initialize SM64 passthrough bridge.",
                    exception
            );
            socket = null;
        }
    }

    public static void tick(Minecraft client) {
        if (socket == null || client.player == null || client.level == null) {
            previousAttackDown = false;
            return;
        }

        ItemStack held = client.player.getMainHandItem();
        String itemId = BuiltInRegistries.ITEM
                .getKey(held.getItem())
                .toString();

        boolean gameplayInput = client.screen == null;
        boolean attackDown = gameplayInput && client.options.keyAttack.isDown();
        boolean useDown = gameplayInput && client.options.keyUse.isDown();

        if (attackDown && !previousAttackDown) {
            attackSerial++;
        }
        previousAttackDown = attackDown;

        CombatProfile combat = CombatProfile.forItem(itemId);

        int forward = gameplayInput && client.options.keyUp.isDown() ? 1 : 0;
        int back = gameplayInput && client.options.keyDown.isDown() ? 1 : 0;
        int left = gameplayInput && client.options.keyLeft.isDown() ? 1 : 0;
        int right = gameplayInput && client.options.keyRight.isDown() ? 1 : 0;
        int jump = gameplayInput && client.options.keyJump.isDown() ? 1 : 0;
        int sneak = gameplayInput && client.player.isShiftKeyDown() ? 1 : 0;
        int sprint = gameplayInput && client.player.isSprinting() ? 1 : 0;

        int start = gameplayInput && Sm64Keys.START.isDown() ? 1 : 0;
        int cameraUp = gameplayInput && Sm64Keys.CAMERA_UP.isDown() ? 1 : 0;
        int cameraDown = gameplayInput && Sm64Keys.CAMERA_DOWN.isDown() ? 1 : 0;
        int cameraLeft = gameplayInput && Sm64Keys.CAMERA_LEFT.isDown() ? 1 : 0;
        int cameraRight = gameplayInput && Sm64Keys.CAMERA_RIGHT.isDown() ? 1 : 0;
        int rTrigger = gameplayInput && Sm64Keys.R_TRIGGER.isDown() ? 1 : 0;
        int lTrigger = gameplayInput && Sm64Keys.L_TRIGGER.isDown() ? 1 : 0;

        String payload = String.format(
                Locale.ROOT,
                "P|%d|%.6f|%.6f|%.6f|%.4f|%.4f|%s|%d|%s|%.2f|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%.3f|%d\n",
                sequence++,
                client.player.getX(),
                client.player.getY(),
                client.player.getZ(),
                client.player.getYRot(),
                client.player.getXRot(),
                sanitize(itemId),
                attackSerial,
                combat.kind,
                combat.reachBlocks,
                combat.power,
                attackDown ? 1 : 0,
                useDown ? 1 : 0,
                forward,
                back,
                left,
                right,
                jump,
                sneak,
                sprint,
                start,
                cameraUp,
                cameraDown,
                cameraLeft,
                cameraRight,
                rTrigger,
                lTrigger,
                client.player.getHealth(),
                client.player.getFoodData().getFoodLevel()
        );

        send(payload);
        receiveAvailable();
    }

    public static boolean isHostConnected() {
        return hostSeen;
    }

    public static HostState hostState() {
        return hostState;
    }

    private static void send(String payload) {
        byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
        DatagramPacket packet = new DatagramPacket(bytes, bytes.length);

        try {
            socket.send(packet);
        } catch (IOException ignored) {
            // The SM64 host may not be running yet.
        }
    }

    private static void receiveAvailable() {
        byte[] buffer = new byte[MAX_PACKET];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);

        for (int i = 0; i < 4; i++) {
            try {
                socket.receive(packet);
            } catch (SocketTimeoutException ignored) {
                return;
            } catch (IOException ignored) {
                return;
            }

            String message = new String(
                    packet.getData(),
                    packet.getOffset(),
                    packet.getLength(),
                    StandardCharsets.UTF_8
            ).trim();

            if (message.startsWith("S|")) {
                parseHostState(message);
            }
        }
    }

    private static void parseHostState(String message) {
        String[] fields = message.split("\\|");
        if (fields.length < 27) {
            return;
        }

        try {
            hostState = new HostState(
                    true,
                    Long.parseLong(fields[1]),
                    Integer.parseInt(fields[2]),
                    Integer.parseInt(fields[3]),
                    Integer.parseInt(fields[4]),
                    Integer.parseInt(fields[5]),
                    Integer.parseInt(fields[6]),
                    Integer.parseInt(fields[7]),
                    Long.parseLong(fields[8]),
                    Long.parseLong(fields[9]),
                    fields[10],
                    Double.parseDouble(fields[11]),
                    Double.parseDouble(fields[12]),
                    Double.parseDouble(fields[13]),
                    Double.parseDouble(fields[14]),
                    Double.parseDouble(fields[15]),
                    Double.parseDouble(fields[16]),
                    Double.parseDouble(fields[17]),
                    Double.parseDouble(fields[18]),
                    Double.parseDouble(fields[19]),
                    Integer.parseInt(fields[20]),
                    Long.parseLong(fields[21]),
                    Integer.parseInt(fields[22]),
                    Integer.parseInt(fields[23]),
                    Double.parseDouble(fields[24]),
                    Integer.parseInt(fields[25]),
                    Integer.parseInt(fields[26])
            );

            if (!hostSeen) {
                hostSeen = true;
                Sm64CrossMod.LOGGER.info(
                        "Connected to native-authority SM64 host."
                );
            }
        } catch (NumberFormatException ignored) {
        }
    }

    private static String sanitize(String value) {
        return value.replace('|', '_').replace('\n', '_').replace('\r', '_');
    }

    private record CombatProfile(String kind, float reachBlocks, int power) {
        private static CombatProfile forItem(String itemId) {
            String path = itemId;
            int separator = path.indexOf(':');
            if (separator >= 0) {
                path = path.substring(separator + 1);
            }

            if (path.endsWith("_sword")) {
                if (path.startsWith("netherite_")) {
                    return new CombatProfile("sword", 3.4f, 6);
                }
                if (path.startsWith("diamond_")) {
                    return new CombatProfile("sword", 3.4f, 5);
                }
                if (path.startsWith("iron_")) {
                    return new CombatProfile("sword", 3.3f, 4);
                }
                return new CombatProfile("sword", 3.2f, 3);
            }

            if (path.endsWith("_axe")) {
                return new CombatProfile("axe", 3.2f, 5);
            }

            if (path.equals("bow") || path.equals("crossbow")) {
                return new CombatProfile("ranged", 24.0f, 4);
            }

            if (path.equals("trident")) {
                return new CombatProfile("trident", 4.5f, 5);
            }

            if (path.equals("mace")) {
                return new CombatProfile("mace", 3.2f, 7);
            }

            if (path.endsWith("_pickaxe")
                    || path.endsWith("_shovel")
                    || path.endsWith("_hoe")) {
                return new CombatProfile("tool", 3.0f, 2);
            }

            return new CombatProfile("hand", 2.7f, 1);
        }
    }

    public record HostState(
            boolean connected,
            long acknowledgedSequence,
            int level,
            int area,
            int course,
            int act,
            int stars,
            int health,
            long saveFlags,
            long courseStarFlags,
            String status,
            double playerX,
            double playerY,
            double playerZ,
            double cameraX,
            double cameraY,
            double cameraZ,
            double focusX,
            double focusY,
            double focusZ,
            int cameraMode,
            long lastHitAttackSerial,
            int hitCount,
            int faceAngle,
            double cameraFov,
            int coins,
            int lives
    ) {
        static HostState disconnected() {
            return new HostState(
                    false, -1, -1, -1, -1, -1, 0, 0,
                    0L, 0L, "disconnected",
                    0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0,
                    0, -1, 0, 0, 45.0, 0, 4
            );
        }
    }
}
