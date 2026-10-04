package dev.eiersohn.sm64cross.client.bridge;

import java.util.Locale;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ItemStack;

/**
 * Hidden Minecraft guest -> visible SM64 host state.
 *
 * Keyboard/mouse input is intentionally NOT read here anymore. The visible
 * SM64 window owns input. Minecraft only reports the currently selected item,
 * hotbar slot and GUI state so SM64 can apply Minecraft item semantics.
 */
public final class InputPublisher {
    private static long sequence;

    private InputPublisher() {
    }

    public static void tick(Minecraft client) {
        if (!HostLink.connected()
                || client.player == null
                || client.level == null) {
            return;
        }

        ItemStack stack = client.player.getMainHandItem();
        String item = BuiltInRegistries.ITEM
                .getKey(stack.getItem())
                .toString();

        CombatProfile combat = CombatProfile.forItem(item);

        HostLink.broadcastMessage(String.format(
                Locale.ROOT,
                "{\"t\":\"guest\",\"seq\":%d,\"item\":\"%s\","
                        + "\"slot\":%d,\"weapon\":\"%s\","
                        + "\"reach\":%.3f,\"power\":%d,\"screen\":%d,"
                        + "\"health\":%.3f,\"food\":%d}",
                sequence++,
                escape(item),
                client.player.getInventory().selected,
                combat.kind,
                combat.reach,
                combat.power,
                client.screen == null ? 0 : 1,
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
