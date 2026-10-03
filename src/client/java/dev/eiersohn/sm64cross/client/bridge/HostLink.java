package dev.eiersohn.sm64cross.client.bridge;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.render.Sm64FrameExporter;
import java.net.InetSocketAddress;
import java.util.Locale;
import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

/**
 * Same topology as universal-modder's minecraft-gta5-passthrough:
 * Minecraft is a localhost WebSocket server and the host game connects to it.
 */
public final class HostLink extends WebSocketServer {
    public static final int DEFAULT_PORT = 25599;
    private static HostLink instance;

    private HostLink(int port) {
        super(new InetSocketAddress("127.0.0.1", port));
        setReuseAddr(true);
        setDaemon(true);
    }

    public static void launch() {
        if (instance != null) {
            return;
        }

        int port = Integer.getInteger("sm64cross.port", DEFAULT_PORT);
        instance = new HostLink(port);
        instance.start();
    }

    public static boolean connected() {
        HostLink link = instance;
        return link != null && !link.getConnections().isEmpty();
    }

    public static void broadcastMessage(String message) {
        HostLink link = instance;
        if (link != null) {
            link.broadcast(message);
        }
    }

    @Override
    public void onStart() {
        Sm64CrossMod.LOGGER.info(
                "SM64 host link listening on 127.0.0.1:{}",
                getPort()
        );
    }

    @Override
    public void onOpen(WebSocket connection, ClientHandshake handshake) {
        Sm64CrossMod.LOGGER.info(
                "SM64 host connected from {}",
                connection.getRemoteSocketAddress()
        );

        connection.send(String.format(
                Locale.ROOT,
                "{\"t\":\"hello\",\"v\":1,\"shm\":\"%s\",\"pid\":%d}",
                Sm64FrameExporter.NAME.replace("\\", "\\\\"),
                ProcessHandle.current().pid()
        ));
    }

    @Override
    public void onClose(
            WebSocket connection,
            int code,
            String reason,
            boolean remote
    ) {
        HostState.disconnect();
        Sm64CrossMod.LOGGER.info(
                "SM64 host disconnected ({} {})",
                code,
                reason
        );
    }

    @Override
    public void onMessage(WebSocket connection, String message) {
        try {
            JsonObject json = JsonParser
                    .parseString(message)
                    .getAsJsonObject();

            String type = json.get("t").getAsString();
            if ("cam".equals(type)) {
                HostState.update(json);
            }
        } catch (RuntimeException exception) {
            Sm64CrossMod.LOGGER.warn(
                    "Bad SM64 host message: {}",
                    exception.toString()
            );
        }
    }

    @Override
    public void onError(WebSocket connection, Exception exception) {
        Sm64CrossMod.LOGGER.warn(
                "SM64 host WebSocket error",
                exception
        );
    }
}
