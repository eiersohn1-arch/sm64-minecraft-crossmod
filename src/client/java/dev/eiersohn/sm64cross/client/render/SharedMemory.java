package dev.eiersohn.sm64cross.client.render;

import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.WString;
import com.sun.jna.win32.StdCallLibrary;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * Win32 named pagefile-backed shared memory, matching universal-modder's
 * Local\\MCPassthroughFrame transport.
 */
final class SharedMemory implements AutoCloseable {
    private static final int PAGE_READWRITE = 0x04;
    private static final int FILE_MAP_ALL_ACCESS = 0xF001F;

    private interface Kernel32 extends StdCallLibrary {
        Kernel32 INSTANCE = Native.load(
                "kernel32",
                Kernel32.class
        );

        Pointer CreateFileMappingW(
                Pointer file,
                Pointer attributes,
                int protect,
                int maximumSizeHigh,
                int maximumSizeLow,
                WString name
        );

        Pointer MapViewOfFile(
                Pointer mapping,
                int desiredAccess,
                int offsetHigh,
                int offsetLow,
                long bytes
        );

        boolean UnmapViewOfFile(Pointer address);

        boolean CloseHandle(Pointer handle);
    }

    private final Pointer mapping;
    private final Pointer view;
    private final long size;

    private SharedMemory(Pointer mapping, Pointer view, long size) {
        this.mapping = mapping;
        this.view = view;
        this.size = size;
    }

    static SharedMemory create(String name, long size) {
        if (!System.getProperty("os.name", "")
                .toLowerCase()
                .contains("win")) {
            throw new IllegalStateException(
                    "Named passthrough shared memory requires Windows"
            );
        }

        Pointer invalidFile = Pointer.createConstant(-1L);
        Pointer mapping = Kernel32.INSTANCE.CreateFileMappingW(
                invalidFile,
                null,
                PAGE_READWRITE,
                (int) (size >>> 32),
                (int) size,
                new WString(name)
        );

        if (mapping == null || Pointer.nativeValue(mapping) == 0L) {
            throw new IllegalStateException(
                    "CreateFileMappingW failed for " + name
            );
        }

        Pointer view = Kernel32.INSTANCE.MapViewOfFile(
                mapping,
                FILE_MAP_ALL_ACCESS,
                0,
                0,
                size
        );

        if (view == null || Pointer.nativeValue(view) == 0L) {
            Kernel32.INSTANCE.CloseHandle(mapping);
            throw new IllegalStateException(
                    "MapViewOfFile failed for " + name
            );
        }

        return new SharedMemory(mapping, view, size);
    }

    ByteBuffer slice(long offset, int length) {
        if (offset < 0 || length < 0 || offset + length > size) {
            throw new IndexOutOfBoundsException();
        }

        return view.getByteBuffer(offset, length)
                .order(ByteOrder.LITTLE_ENDIAN);
    }

    void putInt(long offset, int value) {
        view.setInt(offset, value);
    }

    void putLong(long offset, long value) {
        view.setLong(offset, value);
    }

    void putFloat(long offset, float value) {
        view.setFloat(offset, value);
    }

    void putDouble(long offset, double value) {
        view.setDouble(offset, value);
    }

    long getLong(long offset) {
        return view.getLong(offset);
    }

    @Override
    public void close() {
        Kernel32.INSTANCE.UnmapViewOfFile(view);
        Kernel32.INSTANCE.CloseHandle(mapping);
    }
}
