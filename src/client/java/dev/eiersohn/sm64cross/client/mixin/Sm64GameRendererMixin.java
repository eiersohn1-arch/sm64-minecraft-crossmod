package dev.eiersohn.sm64cross.client.mixin;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import dev.eiersohn.sm64cross.client.render.Sm64FrameExporter;
import net.minecraft.client.Camera;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.renderer.GameRenderer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(GameRenderer.class)
abstract class Sm64GameRendererMixin {
    @Inject(
            method = "renderLevel",
            at = @At(
                    value = "INVOKE",
                    target = "Lnet/minecraft/client/renderer/GameRenderer;renderItemInHand(Lnet/minecraft/client/Camera;FLorg/joml/Matrix4f;)V"
            )
    )
    private void sm64cross$captureWorld(CallbackInfo ci) {
        Sm64FrameExporter.captureWorld();
    }

    @Inject(method = "render", at = @At("TAIL"))
    private void sm64cross$captureOverlay(
            DeltaTracker deltaTracker,
            boolean renderLevel,
            CallbackInfo ci
    ) {
        Sm64FrameExporter.captureOverlay();
    }

    @Inject(method = "getFov", at = @At("HEAD"), cancellable = true)
    private void sm64cross$fov(
            Camera camera,
            float partialTick,
            boolean useFovSetting,
            CallbackInfoReturnable<Double> cir
    ) {
        HostState.State state = HostState.latest();
        if (state.connected()
                && state.fov() > 1.0f
                && state.fov() < 170.0f) {
            cir.setReturnValue((double) state.fov());
        }
    }
}
