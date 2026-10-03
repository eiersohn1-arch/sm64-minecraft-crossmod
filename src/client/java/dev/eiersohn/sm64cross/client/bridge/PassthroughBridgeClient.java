package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.Sm64CrossMod;
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
    private static final int MAX_PACKET = 1024;

    private static DatagramSocket socket;
    private static long sequence;
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
            return;
        }

        ItemStack held = client.player.getMainHandItem();
        String itemId = BuiltInRegistries.ITEM
                .getKey(held.getItem())
                .toString();

        boolean attack = client.options.keyAttack.isDown();
        boolean use = client.options.keyUse.isDown();

        String payload = String.format(
                Locale.ROOT,
                "P|%d|%.6f|%.6f|%.6f|%.4f|%.4f|%s|%d|%d|%d|%d|%.3f|%d\n",
                sequence++,
                client.player.getX(),
                client.player.getY(),
                client.player.getZ(),
                client.player.getYRot(),
                client.player.getXRot(),
                sanitize(itemId),
                attack ? 1 : 0,
                use ? 1 : 0,
                client.player.isShiftKeyDown() ? 1 : 0,
                client.player.isSprinting() ? 1 : 0,
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
            // UDP is intentionally best-effort. The SM64 host may not be running yet.
        }
    }

    private static void receiveAvailable() {
        byte[] buffer = new byte[MAX_PACKET];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);

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

        if (!message.startsWith("S|")) {
            return;
        }

        String[] fields = message.split("\\|");
        if (fields.length < 7) {
            return;
        }

        try {
            HostState next = new HostState(
                    true,
                    Long.parseLong(fields[1]),
                    Integer.parseInt(fields[2]),
                    Integer.parseInt(fields[3]),
                    Integer.parseInt(fields[4]),
                    Integer.parseInt(fields[5]),
                    fields[6]
            );

            hostState = next;

            if (!hostSeen) {
                hostSeen = true;
                Sm64CrossMod.LOGGER.info(
                        "Connected to SM64 passthrough host."
                );
            }
        } catch (NumberFormatException ignored) {
        }
    }

    private static String sanitize(String value) {
        return value.replace('|', '_').replace('\n', '_').replace('\r', '_');
    }

    public record HostState(
            boolean connected,
            long acknowledgedSequence,
            int level,
            int area,
            int stars,
            int health,
            String status
    ) {
        static HostState disconnected() {
            return new HostState(
                    false,
                    -1,
                    -1,
                    -1,
                    0,
                    0,
                    "disconnected"
            );
        }
    }
}
