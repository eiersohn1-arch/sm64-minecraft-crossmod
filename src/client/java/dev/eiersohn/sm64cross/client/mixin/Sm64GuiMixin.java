package dev.eiersohn.sm64cross.client.mixin;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import net.minecraft.client.gui.Gui;
import net.minecraft.client.gui.GuiGraphics;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Replaces only the low-resolution vanilla heart/food/armor/air sprite strip.
 * Hotbar, item icons, XP, effects, chat and every screen remain vanilla.
 */
@Mixin(Gui.class)
abstract class Sm64GuiMixin {
    @Inject(
            method = "renderPlayerHealth",
            at = @At("HEAD"),
            cancellable = true
    )
    private void sm64cross$smoothVitals(
            GuiGraphics graphics,
            CallbackInfo ci
    ) {
        if (HostState.connected()) {
            ci.cancel();
        }
    }
}
