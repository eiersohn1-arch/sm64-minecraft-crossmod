package dev.eiersohn.sm64cross.client.render;

import dev.eiersohn.sm64cross.client.bridge.HostState;
import net.minecraft.client.CameraType;
import net.minecraft.client.Minecraft;

/**
 * Makes Minecraft use the same perspective mode as the visible SM64 host.
 *
 * This matters for much more than camera placement: vanilla uses CameraType to
 * decide whether the local player body is rendered, whether the first-person
 * ItemInHandRenderer runs, and which third-person orientation is active.
 */
public final class Sm64PerspectiveSync {
    private static CameraType restoreType;
    private static boolean owned;

    private Sm64PerspectiveSync() {
    }

    public static void apply(Minecraft client) {
        HostState.State state = HostState.latest();

        if (!state.connected()) {
            if (owned && restoreType != null) {
                client.options.setCameraType(restoreType);
            }
            owned = false;
            restoreType = null;
            return;
        }

        if (!owned) {
            restoreType = client.options.getCameraType();
            owned = true;
        }

        CameraType desired = switch (state.viewMode()) {
            case 1 -> CameraType.THIRD_PERSON_BACK;
            case 2 -> CameraType.THIRD_PERSON_FRONT;
            default -> CameraType.FIRST_PERSON;
        };

        if (client.options.getCameraType() != desired) {
            client.options.setCameraType(desired);
        }
    }
}
