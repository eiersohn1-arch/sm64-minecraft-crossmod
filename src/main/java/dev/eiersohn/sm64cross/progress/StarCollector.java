package dev.eiersohn.sm64cross.progress;

import dev.eiersohn.sm64cross.Sm64CrossMod;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;

public final class StarCollector {
    private StarCollector() {}

    public static void register() {
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            for (ServerPlayer player : server.getPlayerList().getPlayers()) {
                collectFromInventory(player);
            }
        });
    }

    private static void collectFromInventory(ServerPlayer player) {
        int collected = 0;
        for (int slot = 0; slot < player.getInventory().getContainerSize(); slot++) {
            ItemStack stack = player.getInventory().getItem(slot);
            if (stack.is(Sm64CrossMod.POWER_STAR)) {
                collected += stack.getCount();
                stack.setCount(0);
            }
        }

        if (collected > 0) {
            int total = Sm64CrossMod.STAR_STORE.add(player.getUUID(), collected);
            player.sendSystemMessage(Component.literal(
                    "Power Star +" + collected + "  (" + total + "/120)"
            ));
        }
    }
}
