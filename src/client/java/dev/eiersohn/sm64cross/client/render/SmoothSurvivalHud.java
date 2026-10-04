package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;

/**
 * Flat-resolution vitals for the crossmod.
 *
 * Vanilla's 9x9 heart/food sprites are deliberately pixel-art. They become
 * especially chunky when a smaller hidden Minecraft framebuffer is scaled up
 * into the SM64 window. The crossmod replaces only those vitals with clean
 * solid bars; the real Minecraft hotbar, item icons, XP and GUI remain.
 */
public final class SmoothSurvivalHud {
    private static final int BACKGROUND = 0xB0181818;
    private static final int HEALTH = 0xFFE94B4B;
    private static final int ABSORPTION = 0xFFFFC857;
    private static final int FOOD = 0xFFF0B94A;
    private static final int ARMOR = 0xFF9CC7E8;
    private static final int AIR = 0xFF62C8F4;

    private SmoothSurvivalHud() {
    }

    public static void register() {
        HudRenderCallback.EVENT.register((graphics, deltaTracker) -> {
            if (!HostState.connected()) {
                return;
            }

            Minecraft client = Minecraft.getInstance();
            LocalPlayer player = client.player;

            if (player == null || client.options.hideGui) {
                return;
            }

            int center = graphics.guiWidth() / 2;
            int y = graphics.guiHeight() - 39;
            int width = 81;
            int height = 6;

            float healthFraction = fraction(
                    player.getHealth(),
                    player.getMaxHealth()
            );
            float foodFraction =
                    player.getFoodData().getFoodLevel() / 20.0f;

            drawBar(
                    graphics,
                    center - 91,
                    y,
                    width,
                    height,
                    healthFraction,
                    HEALTH
            );
            drawBar(
                    graphics,
                    center + 10,
                    y,
                    width,
                    height,
                    foodFraction,
                    FOOD
            );

            float absorption = player.getAbsorptionAmount();
            if (absorption > 0.0f) {
                drawThinBar(
                        graphics,
                        center - 91,
                        y - 4,
                        width,
                        fraction(absorption, player.getMaxHealth()),
                        ABSORPTION
                );
            }

            int armor = player.getArmorValue();
            if (armor > 0) {
                drawThinBar(
                        graphics,
                        center - 91,
                        y - 8,
                        width,
                        armor / 20.0f,
                        ARMOR
                );
            }

            int maxAir = player.getMaxAirSupply();
            int air = player.getAirSupply();
            if (maxAir > 0 && air < maxAir) {
                drawThinBar(
                        graphics,
                        center + 10,
                        y - 4,
                        width,
                        air / (float) maxAir,
                        AIR
                );
            }
        });
    }

    private static void drawBar(
            net.minecraft.client.gui.GuiGraphics graphics,
            int x,
            int y,
            int width,
            int height,
            float fraction,
            int color
    ) {
        graphics.fill(x, y, x + width, y + height, BACKGROUND);

        int filled = Math.round(
                Math.max(0.0f, Math.min(1.0f, fraction))
                        * width
        );

        if (filled > 0) {
            graphics.fill(
                    x,
                    y,
                    x + filled,
                    y + height,
                    color
            );
        }
    }

    private static void drawThinBar(
            net.minecraft.client.gui.GuiGraphics graphics,
            int x,
            int y,
            int width,
            float fraction,
            int color
    ) {
        graphics.fill(x, y, x + width, y + 2, BACKGROUND);

        int filled = Math.round(
                Math.max(0.0f, Math.min(1.0f, fraction))
                        * width
        );

        if (filled > 0) {
            graphics.fill(x, y, x + filled, y + 2, color);
        }
    }

    private static float fraction(float value, float max) {
        if (max <= 0.0f) {
            return 0.0f;
        }
        return Math.max(0.0f, Math.min(1.0f, value / max));
    }
}
