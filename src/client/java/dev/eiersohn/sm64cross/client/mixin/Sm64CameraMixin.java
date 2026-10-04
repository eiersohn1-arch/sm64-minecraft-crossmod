package dev.eiersohn.sm64cross.client.mixin;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import dev.eiersohn.sm64cross.client.render.Sm64VisualSync;
import net.minecraft.client.Camera;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.BlockGetter;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(Camera.class)
abstract class Sm64CameraMixin {
    @Shadow
    private boolean detached;

    @Shadow
    protected abstract void setPosition(double x, double y, double z);

    @Shadow
    protected abstract void setRotation(float yaw, float pitch);

    @Inject(method = "setup", at = @At("TAIL"))
    private void sm64cross$camera(
            BlockGetter level,
            Entity entity,
            boolean detached,
            boolean reverse,
            float partialTick,
            CallbackInfo ci
    ) {
        HostState.State state = HostState.latest();
        if (!state.connected()) {
            return;
        }

        setPosition(
                state.cameraX(),
                Sm64VisualSync.renderY(state.cameraY()),
                state.cameraZ()
        );
        setRotation(state.yaw(), state.pitch());

        /*
         * F5 mode is owned by the visible SM64 host. First-person keeps the
         * local player attached so vanilla renders the real hand/item.
         * Both third-person modes detach it so Steve's full body is visible.
         */
        this.detached = state.viewMode() != 0;
    }
}
