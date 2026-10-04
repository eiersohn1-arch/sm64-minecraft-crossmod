# Async Minecraft readback

Minecraft 1.21.1 uses OpenGL, while the visible SM64 host uses D3D11. A direct GPU texture share between those APIs would require a much larger native interop layer.

The guest therefore keeps the Universal-Modder MCPT shared-memory contract but no longer performs synchronous `glGetTexImage(ByteBuffer)` reads.

The 1.21.1 exporter now has three PBO capture slots:

1. world colour and depth are queued into GL pixel-pack buffers;
2. the framebuffer is cleared for the transparent HUD layer;
3. the final overlay is queued into its PBO;
4. a GPU fence is inserted;
5. later frames poll the fence with a zero timeout;
6. only completed captures are mapped and copied to `Local\MCPassthroughFrame`.

If all readback slots are busy, the exporter drops a guest frame instead of blocking Minecraft's render thread. SM64's camera-pose reprojection compensates for the short age of the latest completed guest frame.

This is the Minecraft-1.21.1/OpenGL equivalent of the asynchronous GPU-buffer readback used by Universal Modder's newer passthrough example.
