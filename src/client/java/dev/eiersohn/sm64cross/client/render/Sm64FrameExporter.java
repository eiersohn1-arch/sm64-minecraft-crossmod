package dev.eiersohn.sm64cross.client.render;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.systems.RenderSystem;
import dev.eiersohn.sm64cross.Sm64CrossMod;
import dev.eiersohn.sm64cross.client.bridge.PassthroughBridgeClient;
import net.minecraft.client.Minecraft;
import org.lwjgl.glfw.GLFW;
import org.lwjgl.glfw.GLFWNativeWin32;
import org.lwjgl.opengl.GL11;
import org.lwjgl.system.MemoryStack;
import org.lwjgl.system.MemoryUtil;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;

/**
 * Exports Minecraft's transparent 3D contribution and HUD for the SM64 host.
 *
 * <p>The file lives in the user's temp directory and is memory mapped by both
 * processes. It is intentionally a file mapping instead of JNI/JNA so the
 * Fabric side stays pure Java 21.</p>
 *
 * <pre>
 * header (4096 bytes, native little endian)
 *  0  int magic "S64X"
 *  4  int version
 *  8  int width
 * 12  int height
 * 16 long sequence (odd while writing, even when complete)
 * 24 long frame number
 * 32 int flags: bit 0 = rows bottom-up
 * 36 float Minecraft near plane
 * 40 float Minecraft far plane
 * 44 float vertical FOV degrees
 * 48 int Minecraft client-area screen X
 * 52 int Minecraft client-area screen Y
 * 56 int Minecraft client-area window width
 * 60 int Minecraft client-area window height
 * 64 long native Win32 HWND (0 on non-Windows)
 *
 * data:
 * 4096                  world RGBA8
 * 4096 + pixels*4       world depth float32
 * 4096 + pixels*8       overlay RGBA8 (hand + HUD)
 * </pre>
 */
public final class Sm64FrameExporter {
    public static final int MAGIC = 0x58343653; // "S64X"
    public static final int VERSION = 1;
    public static final int HEADER = 4096;
    public static final int MAX_WIDTH = 3840;
    public static final int MAX_HEIGHT = 2160;
    public static final long MAX_PIXELS =
            (long) MAX_WIDTH * MAX_HEIGHT;
    public static final long FILE_BYTES =
            HEADER + MAX_PIXELS * 12L;

    private static final Path FILE = Path.of(
            System.getProperty("java.io.tmpdir"),
            "sm64cross_frame.bin"
    );

    private static RandomAccessFile randomFile;
    private static FileChannel channel;
    private static MappedByteBuffer mapped;

    private static ByteBuffer world;
    private static ByteBuffer depth;
    private static ByteBuffer overlay;
    private static int capacityBytes;
    private static int capturedWidth;
    private static int capturedHeight;
    private static long sequence;
    private static long frame;
    private static boolean current;
    private static boolean failed;
    private static boolean sizeWarned;

    private Sm64FrameExporter() {
    }

    public static Path path() {
        return FILE;
    }

    public static void captureWorld() {
        if (!PassthroughBridgeClient.isHostConnected()) {
            current = false;
            return;
        }

        RenderSystem.assertOnRenderThread();

        Minecraft minecraft = Minecraft.getInstance();
        RenderTarget target = minecraft.getMainRenderTarget();

        int width = target.width;
        int height = target.height;
        long pixels = (long) width * height;

        if (width <= 0
                || height <= 0
                || width > MAX_WIDTH
                || height > MAX_HEIGHT
                || pixels > MAX_PIXELS) {
            if (!sizeWarned) {
                sizeWarned = true;
                Sm64CrossMod.LOGGER.warn(
                        "SM64 frame export skipped at {}x{}; max is {}x{}",
                        width,
                        height,
                        MAX_WIDTH,
                        MAX_HEIGHT
                );
            }
            current = false;
            return;
        }

        if (!ensureMapping()) {
            current = false;
            return;
        }

        int bytes = Math.toIntExact(pixels * 4L);
        ensureBuffers(bytes);

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
        current = true;

        /*
         * Keep the depth buffer, but wipe the already-rendered world colour.
         * Vanilla then draws the first-person hand and GUI into a transparent
         * colour target. That becomes our screen-space overlay layer.
         */
        target.bindWrite(false);
        GL11.glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
        GL11.glClear(GL11.GL_COLOR_BUFFER_BIT);
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
                || target.height != capturedHeight) {
            return;
        }

        int bytes = capacityBytes;
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

        publish(bytes);
    }

    private static boolean ensureMapping() {
        if (mapped != null) {
            return true;
        }
        if (failed) {
            return false;
        }

        try {
            randomFile = new RandomAccessFile(FILE.toFile(), "rw");
            randomFile.setLength(FILE_BYTES);
            channel = randomFile.getChannel();
            mapped = channel.map(
                    FileChannel.MapMode.READ_WRITE,
                    0,
                    FILE_BYTES
            );
            mapped.order(ByteOrder.LITTLE_ENDIAN);

            mapped.putInt(0, MAGIC);
            mapped.putInt(4, VERSION);
            mapped.putLong(16, 0L);

            Sm64CrossMod.LOGGER.info(
                    "SM64 compositor frame mapping ready at {}",
                    FILE
            );
            return true;
        } catch (IOException exception) {
            failed = true;
            Sm64CrossMod.LOGGER.error(
                    "Could not create SM64 frame mapping",
                    exception
            );
            return false;
        }
    }

    private static void ensureBuffers(int bytes) {
        if (world != null && capacityBytes == bytes) {
            return;
        }

        freeBuffers();

        world = MemoryUtil.memAlloc(bytes);
        depth = MemoryUtil.memAlloc(bytes);
        overlay = MemoryUtil.memAlloc(bytes);
        capacityBytes = bytes;
    }

    private static void freeBuffers() {
        if (world != null) {
            MemoryUtil.memFree(world);
        }
        if (depth != null) {
            MemoryUtil.memFree(depth);
        }
        if (overlay != null) {
            MemoryUtil.memFree(overlay);
        }

        world = null;
        depth = null;
        overlay = null;
        capacityBytes = 0;
    }

    private static void publish(int bytes) {
        long odd = sequence + 1L;
        if ((odd & 1L) == 0L) {
            odd++;
        }

        mapped.putLong(16, odd);
        mapped.putInt(8, capturedWidth);
        mapped.putInt(12, capturedHeight);
        mapped.putLong(24, ++frame);
        mapped.putInt(32, 1);

        Minecraft minecraft = Minecraft.getInstance();
        mapped.putFloat(36, 0.05f);
        mapped.putFloat(
                40,
                Math.max(
                        32.0f,
                        minecraft.gameRenderer.getRenderDistance()
                )
        );

        float fov = (float) PassthroughBridgeClient
                .hostState()
                .cameraFov();
        mapped.putFloat(44, fov);
        publishWindowInfo(minecraft);

        putLayer(HEADER, world, bytes);
        putLayer(HEADER + (long) bytes, depth, bytes);
        putLayer(HEADER + 2L * bytes, overlay, bytes);

        sequence = odd + 1L;
        mapped.putLong(16, sequence);
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

            mapped.putInt(48, x.get(0));
            mapped.putInt(52, y.get(0));
            mapped.putInt(56, width.get(0));
            mapped.putInt(60, height.get(0));
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

        mapped.putLong(64, nativeWindow);
    }

    private static void putLayer(
            long offset,
            ByteBuffer source,
            int bytes
    ) {
        ByteBuffer copy = source.duplicate();
        copy.position(0);
        copy.limit(bytes);

        MappedByteBuffer target = mapped.duplicate();
        target.position(Math.toIntExact(offset));
        target.put(copy);
    }
}
