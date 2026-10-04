package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.bridge.HostState;
import java.nio.IntBuffer;
import net.minecraft.client.Minecraft;
import org.lwjgl.glfw.GLFW;
import org.lwjgl.system.MemoryStack;

/**
 * Keeps Minecraft as a hidden/off-screen guest renderer while SM64 owns the
 * only visible play window.
 *
 * The hidden framebuffer is resized to the host client area so HUD/items are
 * composited 1:1 instead of being enlarged from a fixed 1280x720 image.
 */
public final class BackgroundGuestWindow {
    private static boolean backgrounded;
    private static int restoreX;
    private static int restoreY;
    private static int restoreWidth;
    private static int restoreHeight;
    private static int streamWidth;
    private static int streamHeight;

    private BackgroundGuestWindow() {
    }

    public static void tick(Minecraft client) {
        client.options.pauseOnLostFocus = false;

        HostState.State state = HostState.latest();

        boolean shouldBackground =
                Boolean.parseBoolean(
                        System.getProperty(
                                "sm64cross.backgroundGuest",
                                "true"
                        )
                )
                && state.connected()
                && client.player != null
                && client.level != null;

        long window = client.getWindow().getWindow();

        if (shouldBackground && !backgrounded) {
            try (MemoryStack stack = MemoryStack.stackPush()) {
                IntBuffer x = stack.mallocInt(1);
                IntBuffer y = stack.mallocInt(1);
                IntBuffer width = stack.mallocInt(1);
                IntBuffer height = stack.mallocInt(1);

                GLFW.glfwGetWindowPos(window, x, y);
                GLFW.glfwGetWindowSize(window, width, height);

                restoreX = x.get(0);
                restoreY = y.get(0);
                restoreWidth = width.get(0);
                restoreHeight = height.get(0);
            }

            GLFW.glfwSetWindowPos(window, -32000, -32000);
            GLFW.glfwShowWindow(window);
            backgrounded = true;

            Sm64CrossMod.LOGGER.info(
                    "Minecraft guest moved off-screen; SM64 owns the visible window."
            );
        }

        if (shouldBackground) {
            int desiredWidth = clamp(
                    state.hostWidth(),
                    640,
                    Sm64FrameExporter.MAX_WIDTH
            );
            int desiredHeight = clamp(
                    state.hostHeight(),
                    360,
                    Sm64FrameExporter.MAX_HEIGHT
            );

            if (desiredWidth != streamWidth
                    || desiredHeight != streamHeight) {
                GLFW.glfwSetWindowSize(
                        window,
                        desiredWidth,
                        desiredHeight
                );
                GLFW.glfwSetWindowPos(window, -32000, -32000);
                streamWidth = desiredWidth;
                streamHeight = desiredHeight;

                Sm64CrossMod.LOGGER.info(
                        "Minecraft off-screen framebuffer matched to host: {}x{}",
                        desiredWidth,
                        desiredHeight
                );
            }
        } else if (backgrounded) {
            if (restoreWidth > 0 && restoreHeight > 0) {
                GLFW.glfwSetWindowSize(
                        window,
                        restoreWidth,
                        restoreHeight
                );
            }
            GLFW.glfwSetWindowPos(window, restoreX, restoreY);
            GLFW.glfwShowWindow(window);

            backgrounded = false;
            streamWidth = 0;
            streamHeight = 0;

            Sm64CrossMod.LOGGER.info(
                    "Minecraft guest window restored because the SM64 host disconnected."
            );
        }
    }

    public static boolean isBackgrounded() {
        return backgrounded;
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }
}
