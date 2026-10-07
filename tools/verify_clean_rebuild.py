#!/usr/bin/env python3
"""Verify the real Universal Modder Minecraft passthrough contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SM64 = ROOT / "vendor" / "sm64-port"
UM = ROOT / "vendor" / "universal-modder"
checks = []


def contains(path, needle, name):
    ok = path.is_file() and needle in path.read_text(encoding="utf-8")
    checks.append((name, ok))
    if not ok:
        print("FAIL", name)


def same(a, b, name):
    ok = a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
    checks.append((name, ok))
    if not ok:
        print("FAIL", name)


pc = SM64 / "src" / "pc" / "pc_main.c"
host = SM64 / "src" / "pc" / "sm64_passthrough.cpp"
gfx = SM64 / "src" / "pc" / "gfx" / "gfx_direct3d11.cpp"
dxgi = SM64 / "src" / "pc" / "gfx" / "gfx_dxgi.cpp"
overlay = SM64 / "src" / "pc" / "gfx" / "um_mcpt_overlay.inc"
makefile = SM64 / "Makefile"
ref = UM / "examples" / "minecraft-gta5-passthrough" / "gta" / "src"

same(ref / "ws.cpp", SM64 / "src" / "pc" / "ws.cpp", "Universal Modder ws.cpp verbatim")
same(ref / "ws.h", SM64 / "src" / "pc" / "ws.h", "Universal Modder ws.h verbatim")

contains(pc, "um_passthrough_start", "SM64 starts real UM link")
contains(pc, "um_passthrough_before_frame", "SM64 polls guest before game loop")
contains(pc, "um_passthrough_frame", "SM64 publishes host state every frame")
contains(pc, "um_passthrough_stop", "SM64 stops UM link")

contains(host, "127.0.0.1", "localhost-only UM transport")
contains(host, '{\"t\":\"cam\"', "UM camera protocol")
contains(host, '{\"t\":\"ground\"', "UM collision protocol")
contains(host, '{\"t\":\"key\"', "UM key protocol")
contains(host, '{\"t\":\"move\"', "real Minecraft movement protocol")
contains(host, '{\"t\":\"look\"', "real Minecraft raw-look protocol")
contains(host, '"mcpos"', "Minecraft authoritative pose feedback")
contains(host, "find_floor", "SM64 floor collision sampled")
contains(host, "find_ceil", "SM64 ceiling collision sampled")
contains(host, "find_wall_collisions", "SM64 wall collision sampled")
contains(host, "um_passthrough_neutralize_controller", "Mario controller disabled during MC authority")
contains(host, "um_passthrough_apply_mario_proxy", "Mario is progression proxy for Steve")
contains(host, "um_passthrough_override_camera", "Minecraft look owns normal SM64 camera")
contains(host, "ACT_GROUP_CUTSCENE", "SM64 cutscene authority handoff")
contains(host, "ACT_GROUP_SUBMERGED", "unsupported submerged actions fail back to SM64")

contains(dxgi, "WM_INPUT", "Win32 raw mouse input installed")
contains(dxgi, "RegisterRawInputDevices", "raw mouse device registered")
contains(dxgi, "um_passthrough_key_event", "event-driven keyboard forwarded")
contains(dxgi, "um_passthrough_mouse_button", "mouse buttons forwarded")
contains(dxgi, "um_passthrough_scroll", "hotbar wheel forwarded")
contains(dxgi, "um_passthrough_pointer_locked", "cursor hidden only in gameplay")

contains(gfx, '#include "um_mcpt_overlay.inc"', "MCPT compositor injected")
contains(gfx, "um_draw_mcpt", "MCPT frame drawn inside SM64")
contains(overlay, 'Local\\\\MCPassthroughFrame', "Universal Modder shared-memory mapping")
contains(overlay, "McDepthTex", "real Minecraft depth layer uploaded")
contains(overlay, "SV_DEPTH", "Minecraft world writes per-pixel host depth")
contains(overlay, "D3D11_COMPARISON_LESS_EQUAL", "Minecraft world depth-tests against SM64")
contains(overlay, "PSOverlay", "hand/HUD/screens use separate overlay pass")

contains(makefile, "lws2_32", "Winsock linked")
contains(makefile, "-pthread", "UM websocket worker linked")

contains(SM64 / "src" / "game" / "mario.c", "um_passthrough_neutralize_controller", "Mario movement neutralized")
contains(SM64 / "src" / "game" / "mario.c", "um_passthrough_apply_mario_proxy", "Mario proxy synced")
contains(SM64 / "src" / "game" / "camera.c", "um_passthrough_override_camera", "camera hook installed")
contains(SM64 / "src" / "game" / "hud.c", "um_passthrough_connected", "duplicate SM64 HUD hidden")

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    if ok:
        print("OK  ", name)

if failed:
    raise SystemExit("Universal Modder passthrough verification failed: " + ", ".join(failed))

print("Real Universal Modder Minecraft x SM64 contract: OK")
