package dev.eiersohn.sm64cross;

import dev.eiersohn.sm64cross.command.Sm64Commands;
import dev.eiersohn.sm64cross.importer.CourseBuildService;
import dev.eiersohn.sm64cross.importer.CourseRuntimeService;
import dev.eiersohn.sm64cross.progress.StarCollector;
import dev.eiersohn.sm64cross.progress.StarStore;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.item.CreativeModeTabs;
import net.minecraft.world.item.Item;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class Sm64CrossMod implements ModInitializer {
    public static final String MOD_ID = "sm64cross";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    public static final StarStore STAR_STORE = new StarStore();

    public static final Item POWER_STAR = Registry.register(
            BuiltInRegistries.ITEM,
            id("power_star"),
            new Item(new Item.Properties().stacksTo(64))
    );

    @Override
    public void onInitialize() {
        STAR_STORE.load();
        Sm64Commands.register();
        StarCollector.register();
        CourseBuildService.register();
        CourseRuntimeService.register();

        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.TOOLS_AND_UTILITIES)
                .register(entries -> entries.accept(POWER_STAR));

        LOGGER.info("SM64 × Minecraft Crossmod initialized.");
    }

    public static ResourceLocation id(String path) {
        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);
    }
}
