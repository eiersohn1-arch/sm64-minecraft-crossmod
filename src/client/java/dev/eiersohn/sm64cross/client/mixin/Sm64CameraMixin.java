package dev.eiersohn.sm64cross.client.mixin;

import dev.eiersohn.sm64cross.client.bridge.PassthroughBridgeClient;
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
    protected abstract void setPosition(
            double x,
            double y,
            double z
    );

    @Shadow
    protected abstract void setRotation(
            float yaw,
            float pitch,
            float roll
    );

    @Inject(method = "setup", at = @At("TAIL"))
    private void sm64cross$camera(
            BlockGetter level,
            Entity entity,
            boolean detached,
            boolean reverse,
            float partialTick,
            CallbackInfo ci
    ) {
        PassthroughBridgeClient.HostState state =
                PassthroughBridgeClient.hostState();

        if (!state.connected()) {
            return;
        }

        double cx = Sm64VisualSync.x(state.cameraX());
        double cy = Sm64VisualSync.y(state.cameraY());
        double cz = Sm64VisualSync.z(state.cameraZ());

        double fx = Sm64VisualSync.x(state.focusX());
        double fy = Sm64VisualSync.y(state.focusY());
        double fz = Sm64VisualSync.z(state.focusZ());

        double dx = fx - cx;
        double dy = fy - cy;
        double dz = fz - cz;
        double horizontal = Math.sqrt(dx * dx + dz * dz);

        float yaw = (float) Math.toDegrees(
                Math.atan2(-dx, dz)
        );
        float pitch = (float) -Math.toDegrees(
                Math.atan2(dy, Math.max(horizontal, 1.0e-6))
        );

        this.setPosition(cx, cy, cz);
        this.setRotation(yaw, pitch, 0.0f);

        /*
         * SM64 uses a third-person camera for normal play. Marking the
         * Minecraft camera detached makes vanilla render the local Steve body.
         */
        this.detached = true;
    }
}
