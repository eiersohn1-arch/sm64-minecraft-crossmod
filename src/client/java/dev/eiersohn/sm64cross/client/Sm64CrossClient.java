package dev.eiersohn.sm64cross.client;

import dev.eiersohn.sm64cross.client.bridge.PassthroughBridgeClient;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;

public final class Sm64CrossClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        PassthroughBridgeClient.start();

        ClientTickEvents.END_CLIENT_TICK.register(client ->
                PassthroughBridgeClient.tick(client)
        );
    }
}
