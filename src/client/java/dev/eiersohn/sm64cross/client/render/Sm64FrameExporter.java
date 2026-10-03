package dev.eiersohn.sm64cross.client.render;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.systems.RenderSystem;
import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.bridge.HostLink;
import dev.eiersohn.sm64cross.client.bridge.HostState;
import java.nio.ByteBuffer;
import java.nio.IntBuffer;
import java.util.Locale;
import net.minecraft.client.Minecraft;
import org.lwjgl.glfw.GLFW;
import org.lwjgl.glfw.GLFWNativeWin32;
import org.lwjgl.opengl.GL11;
import org.lwjgl.system.MemoryStack;
import org.lwjgl.system.MemoryUtil;

/**
 * Minecraft frame export using the same shared-memory contract as
 * universal-modder/examples/minecraft-gta5-passthrough.
 *
 * <pre>
 * header (4096 bytes, little endian)
 *  0 int magic "MCPT"   4 int version   8 int header bytes   12 int slots
 * 16 long slot stride   24 int max width   28 int max height
 * 32 long publish counter   40 int latest slot   44 int Minecraft pid
 *
 * 256 + 128 * slot:
 *  +0 long seq (odd while writing)
 *  +8 long Minecraft frame
 * +16 long host frame
 * +24 int width   +28 int height
 * +32 float near  +36 float far  +40 float vertical fov
 * +44 int flags: 1=[0,1] depth, 2=rows bottom-up, 4=reversed Z
 * +48 double camera x/y/z
 * +72 float yaw  +76 pitch  +80 roll  +84 int first person
 * +88 long capture nanos  +96 long publish nanos
 *
 * slot data at 4096 + slot*stride:
 * world RGBA8, world depth float32, overlay RGBA8
 * </pre>
 *
 * Offsets 48..64 in the global header are a backwards-compatible SM64
 * extension containing Minecraft's window rectangle/HWND for the temporary
 * click-through host-window integration.
 */
public final class Sm64FrameExporter {
    public static final String NAME = "Local\\MCPassthroughFrame";

    public static final int MAGIC = 0x5450434D; // "MCPT"
    public static final int VERSION = 1;
    public static final int HEADER = 4096;
    public static final int SLOTS = 3;
    public static final int SLOT_DESC = 256;
    public static final int SLOT_DESC_BYTES = 128;
    public static final int MAX_WIDTH = 3840;
    public static final int MAX_HEIGHT = 2160;
    public static final long LAYER_MAX =
            (long) MAX_WIDTH * MAX_HEIGHT * 4L;
    public static final long STRIDE = LAYER_MAX * 3L;
    public static final long MAPPING_BYTES =
            HEADER + STRIDE * SLOTS;

    private static SharedMemory shared;
    private static boolean failed;
    private static boolean warnedSize;

    private static ByteBuffer world;
    private static ByteBuffer depth;
    private static ByteBuffer overlay;
    private static int bufferBytes;

    private static int capturedWidth;
    private static int capturedHeight;
    private static HostState.State capturedPose;
    private static long captureNanos;
    private static boolean current;

    private static int slotNext;
    private static long frameCounter;
    private static long publishCounter;

    private Sm64FrameExporter() {
    }

    public static void captureWorld() {
        HostState.State pose = HostState.latest();
        if (!HostLink.connected() || !pose.connected()) {
            current = false;
            return;
        }

        RenderSystem.assertOnRenderThread();

        Minecraft minecraft = Minecraft.getInstance();
        RenderTarget target = minecraft.getMainRenderTarget();
        int width = target.width;
        int height = target.height;
        long bytes = (long) width * height * 4L;

        if (width <= 0
                || height <= 0
                || width > MAX_WIDTH
                || height > MAX_HEIGHT
                || bytes > LAYER_MAX) {
            if (!warnedSize) {
                warnedSize = true;
                Sm64CrossMod.LOGGER.warn(
                        "Passthrough export skipped at {}x{}; max {}x{}",
                        width,
                        height,
                        MAX_WIDTH,
                        MAX_HEIGHT
                );
            }
            current = false;
            return;
        }

        if (!ensureSharedMemory()) {
            current = false;
            return;
        }

        int size = Math.toIntExact(bytes);
        ensureBuffers(size);

        GL11.glPixelStorei(GL11.GL_PACK_ALIGNMENT, 1);

        world.clear();
        GL11.glBindTexture(
                GL11.GL_TEXTURE_2D,
                target.getColorTextureId()
        );
        GL11.glGetTexImage(
                GL11.GL_TEXTURE_2D,
                0,
                GL11.GL_RGBA,
                GL11.GL_UNSIGNED_BYTE,
                world
        );

        depth.clear();
        GL11.glBindTexture(
                GL11.GL_TEXTURE_2D,
                target.getDepthTextureId()
        );
        GL11.glGetTexImage(
                GL11.GL_TEXTURE_2D,
                0,
                GL11.GL_DEPTH_COMPONENT,
                GL11.GL_FLOAT,
                depth
        );

        capturedWidth = width;
        capturedHeight = height;
        capturedPose = pose;
        captureNanos = System.nanoTime();
        current = true;

        // Match the universal-modder split: world first, then transparent hand/HUD.
        target.bindWrite(false);

        /*
         * glClear obeys the current colour-write mask and scissor state.
         * Minecraft can leave either state changed by previous render passes;
         * if alpha is masked off, clearing to transparent black leaves the old
         * alpha=1 behind. The host then sees an opaque black fullscreen overlay.
         *
         * Force a true full-target RGBA clear before hand/HUD rendering.
         */
        boolean scissorWasEnabled =
                GL11.glIsEnabled(GL11.GL_SCISSOR_TEST);

        ByteBuffer colourMask = MemoryUtil.memAlloc(4);
        try {
            GL11.glGetBooleanv(GL11.GL_COLOR_WRITEMASK, colourMask);

            GL11.glDisable(GL11.GL_SCISSOR_TEST);
            GL11.glColorMask(true, true, true, true);
            GL11.glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
            GL11.glClear(GL11.GL_COLOR_BUFFER_BIT);

            GL11.glColorMask(
                    colourMask.get(0) != 0,
                    colourMask.get(1) != 0,
                    colourMask.get(2) != 0,
                    colourMask.get(3) != 0
            );

            if (scissorWasEnabled) {
                GL11.glEnable(GL11.GL_SCISSOR_TEST);
            }
        } finally {
            MemoryUtil.memFree(colourMask);
        }
    }

    public static void captureOverlay() {
        if (!current) {
            return;
        }
        current = false;

        RenderSystem.assertOnRenderThread();

        Minecraft minecraft = Minecraft.getInstance();
        RenderTarget target = minecraft.getMainRenderTarget();

        if (target.width != capturedWidth
                || target.height != capturedHeight
                || capturedPose == null) {
            return;
        }

        overlay.clear();
        GL11.glBindTexture(
                GL11.GL_TEXTURE_2D,
                target.getColorTextureId()
        );
        GL11.glGetTexImage(
                GL11.GL_TEXTURE_2D,
                0,
                GL11.GL_RGBA,
                GL11.GL_UNSIGNED_BYTE,
                overlay
        );

        publish(minecraft);
    }

    private static boolean ensureSharedMemory() {
        if (shared != null) {
            return true;
        }
        if (failed) {
            return false;
        }

        try {
            shared = SharedMemory.create(NAME, MAPPING_BYTES);
            shared.putInt(0, MAGIC);
            shared.putInt(4, VERSION);
            shared.putInt(8, HEADER);
            shared.putInt(12, SLOTS);
            shared.putLong(16, STRIDE);
            shared.putInt(24, MAX_WIDTH);
            shared.putInt(28, MAX_HEIGHT);
            shared.putLong(32, 0L);
            shared.putInt(40, -1);
            shared.putInt(44, (int) ProcessHandle.current().pid());

            Sm64CrossMod.LOGGER.info(
                    "Passthrough shared memory ready: {} ({} MB)",
                    NAME,
                    MAPPING_BYTES >> 20
            );
            return true;
        } catch (Throwable throwable) {
            failed = true;
            Sm64CrossMod.LOGGER.error(
                    "Could not create passthrough shared memory",
                    throwable
            );
            return false;
        }
    }

    private static void ensureBuffers(int bytes) {
        if (world != null && bufferBytes == bytes) {
            return;
        }

        freeBuffers();
        world = MemoryUtil.memAlloc(bytes);
        depth = MemoryUtil.memAlloc(bytes);
        overlay = MemoryUtil.memAlloc(bytes);
        bufferBytes = bytes;
    }

    private static void freeBuffers() {
        if (world != null) MemoryUtil.memFree(world);
        if (depth != null) MemoryUtil.memFree(depth);
        if (overlay != null) MemoryUtil.memFree(overlay);
        world = null;
        depth = null;
        overlay = null;
        bufferBytes = 0;
    }

    private static void publish(Minecraft minecraft) {
        int slot = slotNext;
        slotNext = (slotNext + 1) % SLOTS;

        long desc = SLOT_DESC + (long) SLOT_DESC_BYTES * slot;
        long seq = shared.getLong(desc);
        if ((seq & 1L) != 0L) {
            seq++;
        }

        // Mark the slot busy before touching its layers.
        shared.putLong(desc, seq + 1L);
        java.lang.invoke.VarHandle.fullFence();

        long frame = ++frameCounter;
        long layerBytes = (long) capturedWidth * capturedHeight * 4L;
        long base = HEADER + STRIDE * slot;

        copy(base, world, Math.toIntExact(layerBytes));
        copy(base + layerBytes, depth, Math.toIntExact(layerBytes));
        copy(base + 2L * layerBytes, overlay, Math.toIntExact(layerBytes));

        float near = 0.05f;
        float far = Math.max(
                32.0f,
                minecraft.gameRenderer.getRenderDistance()
        );

        HostState.State pose = capturedPose;

        shared.putLong(desc + 8, frame);
        shared.putLong(desc + 16, pose.hostFrame());
        shared.putInt(desc + 24, capturedWidth);
        shared.putInt(desc + 28, capturedHeight);
        shared.putFloat(desc + 32, near);
        shared.putFloat(desc + 36, far);
        shared.putFloat(desc + 40, pose.fov());

        // MC 1.21.1 OpenGL depth is [0,1], rows returned bottom-up,
        // and is not reversed-Z.
        shared.putInt(desc + 44, 1 | 2);

        shared.putDouble(desc + 48, pose.cameraX());
        shared.putDouble(desc + 56, pose.cameraY());
        shared.putDouble(desc + 64, pose.cameraZ());
        shared.putFloat(desc + 72, pose.yaw());
        shared.putFloat(desc + 76, pose.pitch());
        shared.putFloat(desc + 80, pose.roll());
        shared.putInt(desc + 84, 0);
        shared.putLong(desc + 88, captureNanos);
        shared.putLong(desc + 96, System.nanoTime());

        publishWindowInfo(minecraft);

        java.lang.invoke.VarHandle.fullFence();
        shared.putLong(desc, seq + 2L);
        shared.putInt(40, slot);
        java.lang.invoke.VarHandle.fullFence();
        shared.putLong(32, ++publishCounter);
    }

    private static void publishWindowInfo(Minecraft minecraft) {
        long glfwWindow = minecraft.getWindow().getWindow();

        try (MemoryStack stack = MemoryStack.stackPush()) {
            IntBuffer x = stack.mallocInt(1);
            IntBuffer y = stack.mallocInt(1);
            IntBuffer width = stack.mallocInt(1);
            IntBuffer height = stack.mallocInt(1);

            GLFW.glfwGetWindowPos(glfwWindow, x, y);
            GLFW.glfwGetWindowSize(glfwWindow, width, height);

            shared.putInt(48, x.get(0));
            shared.putInt(52, y.get(0));
            shared.putInt(56, width.get(0));
            shared.putInt(60, height.get(0));
        }

        long nativeWindow = 0L;
        if (System.getProperty("os.name", "")
                .toLowerCase(Locale.ROOT)
                .contains("win")) {
            try {
                nativeWindow = GLFWNativeWin32
                        .glfwGetWin32Window(glfwWindow);
            } catch (Throwable ignored) {
                nativeWindow = 0L;
            }
        }
        shared.putLong(64, nativeWindow);
    }

    private static void copy(long offset, ByteBuffer source, int bytes) {
        ByteBuffer src = source.duplicate();
        src.position(0);
        src.limit(bytes);

        ByteBuffer dst = shared.slice(offset, bytes);
        dst.position(0);
        dst.put(src);
    }
}
