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
 * We intentionally move the GLFW window far off-screen instead of minimizing
 * it: minimized windows are commonly throttled by drivers/desktop compositors,
 * while an off-screen visible window keeps its OpenGL framebuffer alive.
 */
public final class BackgroundGuestWindow {
    private static boolean backgrounded;
    private static int restoreX;
    private static int restoreY;

    private BackgroundGuestWindow() {
    }

    public static void tick(Minecraft client) {
        // A hidden guest must keep ticking/rendering when SM64 has focus.
        client.options.pauseOnLostFocus = false;

        boolean shouldBackground =
                Boolean.parseBoolean(
                        System.getProperty(
                                "sm64cross.backgroundGuest",
                                "true"
                        )
                )
                && HostState.connected()
                && client.player != null
                && client.level != null;

        long window = client.getWindow().getWindow();

        if (shouldBackground && !backgrounded) {
            try (MemoryStack stack = MemoryStack.stackPush()) {
                IntBuffer x = stack.mallocInt(1);
                IntBuffer y = stack.mallocInt(1);
                GLFW.glfwGetWindowPos(window, x, y);
                restoreX = x.get(0);
                restoreY = y.get(0);
            }

            /*
             * Leave the window "shown" so the OpenGL swapchain keeps running,
             * but place it outside the virtual desktop. SM64 stays focused.
             */
            GLFW.glfwSetWindowPos(window, -32000, -32000);
            GLFW.glfwShowWindow(window);
            backgrounded = true;

            Sm64CrossMod.LOGGER.info(
                    "Minecraft guest moved off-screen; SM64 is now the visible host window."
            );
        } else if (!shouldBackground && backgrounded) {
            GLFW.glfwSetWindowPos(window, restoreX, restoreY);
            GLFW.glfwShowWindow(window);
            backgrounded = false;

            Sm64CrossMod.LOGGER.info(
                    "Minecraft guest window restored because the SM64 host disconnected."
            );
        }
    }

    public static boolean isBackgrounded() {
        return backgrounded;
    }
}
