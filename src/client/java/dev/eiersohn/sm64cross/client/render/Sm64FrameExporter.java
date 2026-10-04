package dev.eiersohn.sm64cross.client.render;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.systems.RenderSystem;
import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.bridge.HostLink;
import dev.eiersohn.sm64cross.client.bridge.HostState;
import java.nio.ByteBuffer;
import net.minecraft.client.Minecraft;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL15;
import org.lwjgl.opengl.GL21;
import org.lwjgl.opengl.GL30;
import org.lwjgl.opengl.GL32;
import org.lwjgl.system.MemoryUtil;

/**
 * Universal-Modder style Minecraft frame exporter for Minecraft 1.21.1.
 *
 * The original 1.21.1 bridge used direct glGetTexImage(ByteBuffer) calls.
 * Those force the render thread to wait for the GPU. This implementation uses
 * a three-entry Pixel Buffer Object ring plus GL fences, matching the
 * asynchronous intent of Universal Modder's newer GPU-buffer exporter.
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

    private static final int READBACK_RING = 3;

    private static final class Capture {
        int colorPbo;
        int depthPbo;
        int overlayPbo;
        int width;
        int height;
        int bytes;
        long fence;
        boolean busy;
        HostState.State pose;
        long frame;
        long captureNanos;

        void allocate(int newWidth, int newHeight, int newBytes) {
            releaseBuffers();

            colorPbo = createPbo(newBytes);
            depthPbo = createPbo(newBytes);
            overlayPbo = createPbo(newBytes);
            width = newWidth;
            height = newHeight;
            bytes = newBytes;
        }

        void releaseBuffers() {
            if (fence != 0L) {
                GL32.glDeleteSync(fence);
                fence = 0L;
            }
            if (colorPbo != 0) {
                GL15.glDeleteBuffers(colorPbo);
                colorPbo = 0;
            }
            if (depthPbo != 0) {
                GL15.glDeleteBuffers(depthPbo);
                depthPbo = 0;
            }
            if (overlayPbo != 0) {
                GL15.glDeleteBuffers(overlayPbo);
                overlayPbo = 0;
            }
            busy = false;
        }
    }

    private static final Capture[] captures =
            new Capture[READBACK_RING];

    private static SharedMemory shared;
    private static boolean failed;
    private static boolean warnedSize;
    private static int ringNext;
    private static Capture current;

    private static int slotNext;
    private static long frameCounter;
    private static long publishCounter;

    private Sm64FrameExporter() {
    }

    public static void captureWorld() {
        RenderSystem.assertOnRenderThread();

        Minecraft minecraft = Minecraft.getInstance();
        drainReadyCaptures(minecraft);

        HostState.State pose = HostState.latest();
        if (!HostLink.connected() || !pose.connected()) {
            current = null;
            return;
        }

        RenderTarget target = minecraft.getMainRenderTarget();
        int width = target.width;
        int height = target.height;
        long bytesLong = (long) width * height * 4L;

        if (width <= 0
                || height <= 0
                || width > MAX_WIDTH
                || height > MAX_HEIGHT
                || bytesLong > LAYER_MAX) {
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
            current = null;
            return;
        }

        if (!ensureSharedMemory()) {
            current = null;
            return;
        }

        Capture capture = captures[ringNext];
        if (capture == null) {
            capture = new Capture();
            captures[ringNext] = capture;
        }

        /*
         * Never stall Minecraft waiting for an old GPU readback. If all PBO
         * slots are still busy, simply skip this frame; the host's pose
         * reprojection hides short gaps much better than a render-thread stall.
         */
        if (capture.busy) {
            current = null;
            return;
        }

        int bytes = Math.toIntExact(bytesLong);
        if (capture.width != width
                || capture.height != height
                || capture.colorPbo == 0) {
            capture.allocate(width, height, bytes);
        }

        GL11.glPixelStorei(GL11.GL_PACK_ALIGNMENT, 1);

        readTextureToPbo(
                target.getColorTextureId(),
                GL11.GL_RGBA,
                GL11.GL_UNSIGNED_BYTE,
                capture.colorPbo
        );
        readTextureToPbo(
                target.getDepthTextureId(),
                GL11.GL_DEPTH_COMPONENT,
                GL11.GL_FLOAT,
                capture.depthPbo
        );

        capture.pose = pose;
        capture.frame = ++frameCounter;
        capture.captureNanos = System.nanoTime();
        current = capture;

        target.bindWrite(false);
        clearForTransparentOverlay();
    }

    public static void captureOverlay() {
        RenderSystem.assertOnRenderThread();

        Capture capture = current;
        current = null;

        if (capture == null) {
            drainReadyCaptures(Minecraft.getInstance());
            return;
        }

        RenderTarget target =
                Minecraft.getInstance().getMainRenderTarget();

        if (target.width != capture.width
                || target.height != capture.height) {
            return;
        }

        readTextureToPbo(
                target.getColorTextureId(),
                GL11.GL_RGBA,
                GL11.GL_UNSIGNED_BYTE,
                capture.overlayPbo
        );

        capture.fence = GL32.glFenceSync(
                GL32.GL_SYNC_GPU_COMMANDS_COMPLETE,
                0
        );
        capture.busy = true;

        ringNext = (ringNext + 1) % READBACK_RING;

        drainReadyCaptures(Minecraft.getInstance());
    }

    private static int createPbo(int bytes) {
        int pbo = GL15.glGenBuffers();
        GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, pbo);
        GL15.glBufferData(
                GL21.GL_PIXEL_PACK_BUFFER,
                (long) bytes,
                GL15.GL_STREAM_READ
        );
        GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, 0);
        return pbo;
    }

    private static void readTextureToPbo(
            int texture,
            int format,
            int type,
            int pbo
    ) {
        GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, pbo);
        GL11.glBindTexture(GL11.GL_TEXTURE_2D, texture);
        GL11.glGetTexImage(
                GL11.GL_TEXTURE_2D,
                0,
                format,
                type,
                0L
        );
        GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, 0);
    }

    private static void clearForTransparentOverlay() {
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

    private static void drainReadyCaptures(Minecraft minecraft) {
        if (shared == null) {
            return;
        }

        for (Capture capture : captures) {
            if (capture == null || !capture.busy || capture.fence == 0L) {
                continue;
            }

            int status = GL32.glClientWaitSync(
                    capture.fence,
                    0,
                    0L
            );

            if (status != GL32.GL_ALREADY_SIGNALED
                    && status != GL32.GL_CONDITION_SATISFIED) {
                continue;
            }

            try {
                publish(minecraft, capture);
            } finally {
                GL32.glDeleteSync(capture.fence);
                capture.fence = 0L;
                capture.busy = false;
            }
        }
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
            shared.putInt(
                    44,
                    (int) ProcessHandle.current().pid()
            );

            Sm64CrossMod.LOGGER.info(
                    "Async MCPT readback ready: {} ({} MB, {} PBO slots)",
                    NAME,
                    MAPPING_BYTES >> 20,
                    READBACK_RING
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

    private static void publish(
            Minecraft minecraft,
            Capture capture
    ) {
        int slot = slotNext;
        slotNext = (slotNext + 1) % SLOTS;

        long desc =
                SLOT_DESC + (long) SLOT_DESC_BYTES * slot;
        long seq = shared.getLong(desc);

        if ((seq & 1L) != 0L) {
            seq++;
        }

        shared.putLong(desc, seq + 1L);
        java.lang.invoke.VarHandle.fullFence();

        long layerBytes =
                (long) capture.width * capture.height * 4L;
        long base = HEADER + STRIDE * slot;

        copyPbo(
                capture.colorPbo,
                base,
                capture.bytes
        );
        copyPbo(
                capture.depthPbo,
                base + layerBytes,
                capture.bytes
        );
        copyPbo(
                capture.overlayPbo,
                base + 2L * layerBytes,
                capture.bytes
        );

        float near = 0.05f;
        float far = Math.max(
                32.0f,
                minecraft.gameRenderer.getRenderDistance()
        );

        HostState.State pose = capture.pose;

        shared.putLong(desc + 8, capture.frame);
        shared.putLong(desc + 16, pose.hostFrame());
        shared.putInt(desc + 24, capture.width);
        shared.putInt(desc + 28, capture.height);
        shared.putFloat(desc + 32, near);
        shared.putFloat(desc + 36, far);
        shared.putFloat(desc + 40, pose.fov());

        // MC 1.21.1 OpenGL: [0,1] depth, rows bottom-up, standard Z.
        shared.putInt(desc + 44, 1 | 2);

        shared.putDouble(desc + 48, pose.cameraX());
        shared.putDouble(desc + 56, pose.cameraY());
        shared.putDouble(desc + 64, pose.cameraZ());
        shared.putFloat(desc + 72, pose.yaw());
        shared.putFloat(desc + 76, pose.pitch());
        shared.putFloat(desc + 80, pose.roll());
        shared.putInt(desc + 84, 0);
        shared.putLong(desc + 88, capture.captureNanos);
        shared.putLong(desc + 96, System.nanoTime());

        java.lang.invoke.VarHandle.fullFence();
        shared.putLong(desc, seq + 2L);
        shared.putInt(40, slot);
        java.lang.invoke.VarHandle.fullFence();
        shared.putLong(32, ++publishCounter);
    }

    private static void copyPbo(
            int pbo,
            long sharedOffset,
            int bytes
    ) {
        GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, pbo);

        ByteBuffer mapped = GL30.glMapBufferRange(
                GL21.GL_PIXEL_PACK_BUFFER,
                0L,
                bytes,
                GL30.GL_MAP_READ_BIT
        );

        if (mapped == null) {
            GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, 0);
            throw new IllegalStateException(
                    "Could not map passthrough PBO"
            );
        }

        try {
            mapped.position(0);
            mapped.limit(bytes);

            ByteBuffer destination =
                    shared.slice(sharedOffset, bytes);
            destination.position(0);
            destination.put(mapped);
        } finally {
            GL15.glUnmapBuffer(GL21.GL_PIXEL_PACK_BUFFER);
            GL15.glBindBuffer(GL21.GL_PIXEL_PACK_BUFFER, 0);
        }
    }
}
