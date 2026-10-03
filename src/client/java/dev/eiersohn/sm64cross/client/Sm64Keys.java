package dev.eiersohn.sm64cross.client;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.minecraft.client.KeyMapping;
import org.lwjgl.glfw.GLFW;

public final class Sm64Keys {
    public static KeyMapping START;
    public static KeyMapping CAMERA_UP;
    public static KeyMapping CAMERA_DOWN;
    public static KeyMapping CAMERA_LEFT;
    public static KeyMapping CAMERA_RIGHT;
    public static KeyMapping R_TRIGGER;
    public static KeyMapping L_TRIGGER;

    private Sm64Keys() {
    }

    public static void register() {
        START = register("key.sm64cross.start", GLFW.GLFW_KEY_P);
        CAMERA_UP = register("key.sm64cross.camera_up", GLFW.GLFW_KEY_I);
        CAMERA_DOWN = register("key.sm64cross.camera_down", GLFW.GLFW_KEY_K);
        CAMERA_LEFT = register("key.sm64cross.camera_left", GLFW.GLFW_KEY_J);
        CAMERA_RIGHT = register("key.sm64cross.camera_right", GLFW.GLFW_KEY_L);
        R_TRIGGER = register("key.sm64cross.r_trigger", GLFW.GLFW_KEY_O);
        L_TRIGGER = register("key.sm64cross.l_trigger", GLFW.GLFW_KEY_U);
    }

    private static KeyMapping register(String translationKey, int glfwKey) {
        return KeyBindingHelper.registerKeyBinding(
                new KeyMapping(
                        translationKey,
                        InputConstants.Type.KEYSYM,
                        glfwKey,
                        "key.categories.sm64cross"
                )
        );
    }
}
