package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.client.bridge.PassthroughBridgeClient;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.Minecraft;

public final class Sm64Hud {
    private Sm64Hud() {
    }

    public static void register() {
        HudRenderCallback.EVENT.register((graphics, deltaTracker) -> {
            PassthroughBridgeClient.HostState state =
                    PassthroughBridgeClient.hostState();

            if (!state.connected()) {
                return;
            }

            Minecraft minecraft = Minecraft.getInstance();
            int x = 8;
            int y = 8;
            int white = 0xFFFFFFFF;
            int gold = 0xFFFFD54A;

            graphics.drawString(
                    minecraft.font,
                    "STAR " + state.stars() + "/120",
                    x,
                    y,
                    gold,
                    true
            );

            graphics.drawString(
                    minecraft.font,
                    "COINS " + state.coins(),
                    x,
                    y + 11,
                    white,
                    true
            );

            graphics.drawString(
                    minecraft.font,
                    "LIVES " + state.lives(),
                    x,
                    y + 22,
                    white,
                    true
            );

            if (state.course() > 0) {
                graphics.drawString(
                        minecraft.font,
                        "COURSE " + state.course()
                                + "  ACT " + state.act(),
                        x,
                        y + 33,
                        white,
                        true
                );
            }
        });
    }
}
