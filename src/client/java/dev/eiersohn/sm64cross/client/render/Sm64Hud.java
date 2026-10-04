package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.Minecraft;

public final class Sm64Hud {
    private Sm64Hud() {
    }

    public static void register() {
        HudRenderCallback.EVENT.register((graphics, deltaTracker) -> {
            HostState.State state = HostState.latest();
            if (!state.connected()) {
                return;
            }

            Minecraft minecraft = Minecraft.getInstance();
            if (minecraft.options.hideGui) {
                return;
            }

            int x = 10;
            int y = 10;
            int width = state.course() > 0 ? 150 : 118;
            int height = (state.hudFlags() & 0x0040) != 0 ? 55 : 43;

            /*
             * Flat panel at native host resolution. No enlarged N64-style
             * bitmap letters and no text shadow, so progression info stays
             * compact while Minecraft remains the dominant HUD.
             */
            graphics.fill(
                    x - 4,
                    y - 4,
                    x + width,
                    y + height,
                    0x8A101418
            );

            int primary = 0xFFF3F6F8;
            int accent = 0xFFFFD166;

            graphics.drawString(
                    minecraft.font,
                    "Stars  " + state.stars() + " / 120",
                    x, y, accent, false
            );
            graphics.drawString(
                    minecraft.font,
                    "Coins  " + state.coins()
                            + "    Lives  " + state.lives(),
                    x, y + 11, primary, false
            );

            int nextY = y + 22;

            if (state.course() > 0) {
                graphics.drawString(
                        minecraft.font,
                        "Course " + state.course()
                                + "    Act " + state.act(),
                        x, nextY, primary, false
                );
                nextY += 11;
            }

            if ((state.hudFlags() & 0x0040) != 0) {
                int frames = state.timerFrames();
                int minutes = frames / 1800;
                int seconds = (frames - minutes * 1800) / 30;
                int tenths =
                        (frames - minutes * 1800 - seconds * 30) / 3;

                graphics.drawString(
                        minecraft.font,
                        String.format(
                                "Time  %d:%02d.%d",
                                minutes,
                                seconds,
                                tenths
                        ),
                        x, nextY, accent, false
                );
            }
        });
    }
}
