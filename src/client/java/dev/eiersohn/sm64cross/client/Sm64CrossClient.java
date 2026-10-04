package dev.eiersohn.sm64cross.client;

import dev.eiersohn.sm64cross.client.bridge.BlockCollisionPublisher;
import dev.eiersohn.sm64cross.client.bridge.HostLink;
import dev.eiersohn.sm64cross.client.bridge.InputPublisher;
import dev.eiersohn.sm64cross.client.bridge.ServerPlayerSync;
import dev.eiersohn.sm64cross.client.render.BackgroundGuestWindow;
import dev.eiersohn.sm64cross.client.render.Sm64Hud;
import dev.eiersohn.sm64cross.client.render.Sm64PerspectiveSync;
import dev.eiersohn.sm64cross.client.render.Sm64VisualSync;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;

public final class Sm64CrossClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        Sm64Keys.register();
        Sm64Hud.register();
        HostLink.launch();

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            InputPublisher.tick(client);
            Sm64PerspectiveSync.apply(client);
            Sm64VisualSync.apply(client);
            ServerPlayerSync.tick(client);
            BlockCollisionPublisher.tick(client);
            BackgroundGuestWindow.tick(client);
        });
    }
}
