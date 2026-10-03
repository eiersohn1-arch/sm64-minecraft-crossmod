package dev.eiersohn.sm64cross;

import net.fabricmc.api.ModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class Sm64CrossMod implements ModInitializer {
    public static final String MOD_ID = "sm64cross";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    @Override
    public void onInitialize() {
        LOGGER.info("SM64 × Minecraft Crossmod passthrough mode initialized.");
    }
}
