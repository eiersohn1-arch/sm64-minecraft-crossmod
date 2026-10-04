package dev.eiersohn.sm64cross.client.mixin;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import dev.eiersohn.sm64cross.client.render.Sm64FrameExporter;
import net.minecraft.client.Camera;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.renderer.GameRenderer;
import org.joml.Matrix4f;
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

    @Inject(
            method = "renderLevel",
            at = @At("TAIL")
    )
    private void sm64cross$captureThirdPersonWorld(
            CallbackInfo ci
    ) {
        HostState.State state = HostState.latest();

        /*
         * In first person we capture immediately before vanilla draws the
         * ItemInHandRenderer, so the arm/item stays in the screen-space layer.
         *
         * In third person vanilla does not execute that hand-render call at
         * all. Capture at renderLevel TAIL instead so the complete Steve model,
         * armor, cape and held items are exported as 3D world geometry.
         */
        if (state.connected() && state.viewMode() != 0) {
            Sm64FrameExporter.captureWorld();
        }
    }

    @Inject(method = "render", at = @At("TAIL"))
    private void sm64cross$captureOverlay(
            DeltaTracker deltaTracker,
            boolean renderLevel,
            CallbackInfo ci
    ) {
        Sm64FrameExporter.captureOverlay();
    }

    @Inject(
            method = "renderItemInHand",
            at = @At("HEAD"),
            cancellable = true
    )
    private void sm64cross$hideFirstPersonHand(
            Camera camera,
            float partialTick,
            Matrix4f projectionMatrix,
            CallbackInfo ci
    ) {
        HostState.State state = HostState.latest();
        if (state.connected() && state.viewMode() != 0) {
            /*
             * Third-person already renders the selected item on Steve's body.
             * In first-person we deliberately allow vanilla's actual hand and
             * ItemInHandRenderer to run after the world capture.
             */
            ci.cancel();
        }
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
