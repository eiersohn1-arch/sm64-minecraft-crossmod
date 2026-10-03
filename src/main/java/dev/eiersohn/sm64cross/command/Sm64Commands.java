package dev.eiersohn.sm64cross.command;

import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.level.LevelCatalog;
import dev.eiersohn.sm64cross.level.Sm64Level;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;

public final class Sm64Commands {
    private Sm64Commands() {}

    public static void register() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) ->
                dispatcher.register(
                        Commands.literal("sm64")
                                .executes(context -> showStars(context.getSource().getPlayerOrException()))
                                .then(Commands.literal("stars")
                                        .executes(context -> showStars(context.getSource().getPlayerOrException())))
                                .then(Commands.literal("star")
                                        .then(Commands.literal("add")
                                                .requires(source -> source.hasPermission(2))
                                                .then(Commands.argument("amount", IntegerArgumentType.integer(1, 120))
                                                        .executes(context -> {
                                                            ServerPlayer player = context.getSource().getPlayerOrException();
                                                            int amount = IntegerArgumentType.getInteger(context, "amount");
                                                            int total = Sm64CrossMod.STAR_STORE.add(player.getUUID(), amount);
                                                            context.getSource().sendSuccess(
                                                                    () -> Component.literal("Stars: " + total + "/120"), false);
                                                            return total;
                                                        })))
                                        .then(Commands.literal("set")
                                                .requires(source -> source.hasPermission(2))
                                                .then(Commands.argument("amount", IntegerArgumentType.integer(0, 120))
                                                        .executes(context -> {
                                                            ServerPlayer player = context.getSource().getPlayerOrException();
                                                            int amount = IntegerArgumentType.getInteger(context, "amount");
                                                            int total = Sm64CrossMod.STAR_STORE.set(player.getUUID(), amount);
                                                            context.getSource().sendSuccess(
                                                                    () -> Component.literal("Stars set to " + total + "/120"), false);
                                                            return total;
                                                        }))))
                                .then(Commands.literal("level")
                                        .then(Commands.literal("list")
                                                .executes(context -> {
                                                    String names = LevelCatalog.LEVELS.stream()
                                                            .map(Sm64Level::id)
                                                            .reduce((a, b) -> a + ", " + b).orElse("");
                                                    context.getSource().sendSuccess(
                                                            () -> Component.literal(names), false);
                                                    return LevelCatalog.LEVELS.size();
                                                }))
                                        .then(Commands.literal("info")
                                                .then(Commands.argument("id", StringArgumentType.word())
                                                        .executes(context -> {
                                                            String id = StringArgumentType.getString(context, "id");
                                                            Sm64Level level = LevelCatalog.find(id).orElse(null);
                                                            if (level == null) {
                                                                context.getSource().sendFailure(
                                                                        Component.literal("Unknown SM64 level: " + id));
                                                                return 0;
                                                            }
                                                            context.getSource().sendSuccess(
                                                                    () -> Component.literal(level.displayName()
                                                                            + " | type=" + level.kind()
                                                                            + " | stars=" + level.normalStars()), false);
                                                            return 1;
                                                        }))))
                )
        );
    }

    private static int showStars(ServerPlayer player) {
        int stars = Sm64CrossMod.STAR_STORE.get(player.getUUID());
        player.sendSystemMessage(Component.literal("Power Stars: " + stars + "/120"));
        return stars;
    }
}
