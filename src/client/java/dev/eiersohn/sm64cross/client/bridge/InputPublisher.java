package dev.eiersohn.sm64cross.client.bridge;

import dev.eiersohn.sm64cross.client.Sm64Keys;
import java.util.Locale;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ItemStack;

/**
 * Minecraft -> host input/events, equivalent to the event channel in the
 * universal-modder passthrough example.
 */
public final class InputPublisher {
    private static long sequence;
    private static long attackSerial;
    private static long useSerial;
    private static boolean previousAttack;
    private static boolean previousUse;

    private InputPublisher() {
    }

    public static void tick(Minecraft client) {
        if (!HostLink.connected()
                || client.player == null
                || client.level == null) {
            previousAttack = false;
            previousUse = false;
            return;
        }

        boolean gameplay = client.screen == null;
        boolean attack = gameplay && client.options.keyAttack.isDown();
        boolean use = gameplay && client.options.keyUse.isDown();

        if (attack && !previousAttack) {
            attackSerial++;
        }
        if (use && !previousUse) {
            useSerial++;
        }

        previousAttack = attack;
        previousUse = use;

        ItemStack stack = client.player.getMainHandItem();
        String item = BuiltInRegistries.ITEM
                .getKey(stack.getItem())
                .toString();

        CombatProfile combat = CombatProfile.forItem(item);

        int keys = 0;
        if (gameplay && client.options.keyUp.isDown()) keys |= 1;
        if (gameplay && client.options.keyDown.isDown()) keys |= 2;
        if (gameplay && client.options.keyLeft.isDown()) keys |= 4;
        if (gameplay && client.options.keyRight.isDown()) keys |= 8;
        if (gameplay && client.options.keyJump.isDown()) keys |= 16;
        if (gameplay && client.player.isShiftKeyDown()) keys |= 32;
        if (gameplay && client.player.isSprinting()) keys |= 64;
        if (gameplay && Sm64Keys.START.isDown()) keys |= 128;
        if (gameplay && Sm64Keys.CAMERA_UP.isDown()) keys |= 256;
        if (gameplay && Sm64Keys.CAMERA_DOWN.isDown()) keys |= 512;
        if (gameplay && Sm64Keys.CAMERA_LEFT.isDown()) keys |= 1024;
        if (gameplay && Sm64Keys.CAMERA_RIGHT.isDown()) keys |= 2048;
        if (gameplay && Sm64Keys.R_TRIGGER.isDown()) keys |= 4096;
        if (gameplay && Sm64Keys.L_TRIGGER.isDown()) keys |= 8192;

        HostLink.broadcastMessage(String.format(
                Locale.ROOT,
                "{\"t\":\"input\",\"seq\":%d,\"item\":\"%s\","
                        + "\"attack\":%d,\"use\":%d,\"weapon\":\"%s\","
                        + "\"reach\":%.3f,\"power\":%d,"
                        + "\"attackDown\":%d,\"useDown\":%d,\"keys\":%d,"
                        + "\"health\":%.3f,\"food\":%d}",
                sequence++,
                escape(item),
                attackSerial,
                useSerial,
                combat.kind,
                combat.reach,
                combat.power,
                attack ? 1 : 0,
                use ? 1 : 0,
                keys,
                client.player.getHealth(),
                client.player.getFoodData().getFoodLevel()
        ));
    }

    private static String escape(String value) {
        return value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"");
    }

    private record CombatProfile(String kind, float reach, int power) {
        static CombatProfile forItem(String itemId) {
            String path = itemId;
            int colon = path.indexOf(':');
            if (colon >= 0) {
                path = path.substring(colon + 1);
            }

            if (path.endsWith("_sword")) {
                if (path.startsWith("netherite_")) return new CombatProfile("sword", 3.4f, 6);
                if (path.startsWith("diamond_")) return new CombatProfile("sword", 3.4f, 5);
                if (path.startsWith("iron_")) return new CombatProfile("sword", 3.3f, 4);
                return new CombatProfile("sword", 3.2f, 3);
            }
            if (path.endsWith("_axe")) return new CombatProfile("axe", 3.2f, 5);
            if (path.equals("bow") || path.equals("crossbow")) return new CombatProfile("ranged", 24.0f, 4);
            if (path.equals("trident")) return new CombatProfile("trident", 4.5f, 5);
            if (path.equals("tnt")) return new CombatProfile("explosive", 5.0f, 8);
            if (path.equals("mace")) return new CombatProfile("mace", 3.2f, 7);
            if (path.endsWith("_pickaxe")
                    || path.endsWith("_shovel")
                    || path.endsWith("_hoe")) {
                return new CombatProfile("tool", 3.0f, 2);
            }
            return new CombatProfile("hand", 2.7f, 1);
        }
    }
}
