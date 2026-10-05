#!/usr/bin/env python3
"""Patch a clean sm64-port checkout into the first real Universal Modder host.

Nothing from the legacy crossmod is reused. The WebSocket implementation is
copied verbatim from Universal Modder's worked Minecraft passthrough example;
this script only adds a thin SM64 pose adapter and build/lifecycle hooks.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
UM = ROOT / "vendor" / "universal-modder"
SM64 = ROOT / "vendor" / "sm64-port"
REF = UM / "examples" / "minecraft-gta5-passthrough" / "gta" / "src"
PC = SM64 / "src" / "pc"


def patch_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch marker missing in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if not (SM64 / "src" / "game" / "game_init.c").is_file():
    raise SystemExit("Run setup-windows.bat first.")

# Universal Modder transport, verbatim.
for name in ("ws.cpp", "ws.h"):
    shutil.copy2(REF / name, PC / name)

(PC / "sm64_passthrough.h").write_text(r'''#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void um_passthrough_start(void);
void um_passthrough_stop(void);
void um_passthrough_frame(void);
#ifdef __cplusplus
}
#endif
''', encoding="utf-8")

(PC / "sm64_passthrough.cpp").write_text(r'''#include "sm64_passthrough.h"
#include "ws.h"
#include <cmath>
#include <cstdio>

extern "C" {
#include "game/camera.h"
#include "game/level_update.h"
#include "game/mario.h"
}

static WsClient s_ws;
static unsigned long long s_frame = 0;

void um_passthrough_start(void) {
    s_ws.start("127.0.0.1", 25599);
}

void um_passthrough_stop(void) {
    s_ws.stop();
}

void um_passthrough_frame(void) {
    if (!s_ws.connected() || gMarioState == nullptr) {
        return;
    }

    // Keep the transform in one place. Later collision and rendering stages
    // must use these exact same constants.
    constexpr float SCALE = 100.0f;
    constexpr float MC_Y_ORIGIN = 64.0f;
    constexpr float RAD_TO_DEG = 57.29577951308232f;

    const float cameraX = gLakituState.pos[0] / SCALE;
    const float cameraY = gLakituState.pos[1] / SCALE + MC_Y_ORIGIN;
    const float cameraZ = -gLakituState.pos[2] / SCALE;

    const float playerX = gMarioState->pos[0] / SCALE;
    const float playerY = gMarioState->pos[1] / SCALE + MC_Y_ORIGIN;
    const float playerZ = -gMarioState->pos[2] / SCALE;

    const float bodyYaw =
        180.0f
        - (float)gMarioState->faceAngle[1] * (360.0f / 65536.0f);

    // Render Minecraft from the actual SM64 camera, not Mario's body heading.
    const float dx = (gLakituState.focus[0] - gLakituState.pos[0]) / SCALE;
    const float dy = (gLakituState.focus[1] - gLakituState.pos[1]) / SCALE;
    const float dz = -(gLakituState.focus[2] - gLakituState.pos[2]) / SCALE;
    const float cameraYaw = std::atan2(-dx, dz) * RAD_TO_DEG;
    const float cameraPitch =
        -std::atan2(dy, std::sqrt(dx * dx + dz * dz)) * RAD_TO_DEG;

    // Milestone 1 intentionally uses third person. It proves that the real
    // SM64 runtime drives Universal Modder's real Minecraft guest before
    // compositor or collision code is added.
    char message[512];
    std::snprintf(
        message,
        sizeof(message),
        "{\"t\":\"cam\",\"f\":%llu,"
        "\"p\":[%.4f,%.4f,%.4f],"
        "\"r\":[%.3f,%.3f,0],"
        "\"fov\":60,\"fp\":false,"
        "\"pl\":[%.4f,%.4f,%.4f],\"h\":%.3f}",
        ++s_frame,
        cameraX, cameraY, cameraZ,
        cameraYaw, cameraPitch,
        playerX, playerY, playerZ,
        bodyYaw
    );
    s_ws.send(message);
}
''', encoding="utf-8")


# First visible compositor milestone: consume Universal Modder's MCPT frame
# directly inside SM64's native D3D11 renderer. Depth occlusion is added in
# the next milestone; this pass proves the shared-memory/render path first.
gfx = PC / "gfx"
(gfx / "mcpt_sm64_overlay.inc").write_text(r'''constexpr const wchar_t *UM_MCPT_MAPPING = L"Local\\MCPassthroughFrame";
constexpr uint32_t UM_MCPT_MAGIC = 0x5450434D;
constexpr size_t UM_MCPT_HEADER = 4096;
constexpr size_t UM_MCPT_SLOT_DESC = 256;
constexpr size_t UM_MCPT_SLOT_DESC_BYTES = 128;

struct UmMcptOverlayState {
    HANDLE mapping = nullptr;
    const uint8_t *view = nullptr;
    int slots = 0;
    int64_t stride = 0;
    int64_t lastPublish = -1;
    DWORD nextOpenAttempt = 0;

    uint32_t width = 0;
    uint32_t height = 0;
    ComPtr<ID3D11Texture2D> worldTexture;
    ComPtr<ID3D11Texture2D> overlayTexture;
    ComPtr<ID3D11ShaderResourceView> worldSrv;
    ComPtr<ID3D11ShaderResourceView> overlaySrv;

    ComPtr<ID3D11VertexShader> vs;
    ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11SamplerState> sampler;
    ComPtr<ID3D11BlendState> blend;
    ComPtr<ID3D11DepthStencilState> noDepth;
    ComPtr<ID3D11RasterizerState> raster;
    bool pipelineReady = false;
};

static UmMcptOverlayState um_mcpt;

template <typename T>
static T um_mcpt_read(const uint8_t *p) {
    T value;
    std::memcpy(&value, p, sizeof(value));
    return value;
}

static bool um_mcpt_open() {
    if (um_mcpt.view != nullptr) {
        return true;
    }
    DWORD now = GetTickCount();
    if (now < um_mcpt.nextOpenAttempt) {
        return false;
    }
    um_mcpt.nextOpenAttempt = now + 1000;

    um_mcpt.mapping = OpenFileMappingW(FILE_MAP_READ, FALSE, UM_MCPT_MAPPING);
    if (um_mcpt.mapping == nullptr) {
        return false;
    }

    const uint8_t *header = static_cast<const uint8_t *>(
        MapViewOfFile(um_mcpt.mapping, FILE_MAP_READ, 0, 0, UM_MCPT_HEADER)
    );
    if (header == nullptr || um_mcpt_read<uint32_t>(header) != UM_MCPT_MAGIC) {
        if (header != nullptr) UnmapViewOfFile(header);
        CloseHandle(um_mcpt.mapping);
        um_mcpt.mapping = nullptr;
        return false;
    }

    um_mcpt.slots = um_mcpt_read<int32_t>(header + 12);
    um_mcpt.stride = um_mcpt_read<int64_t>(header + 16);
    UnmapViewOfFile(header);

    if (um_mcpt.slots <= 0 || um_mcpt.stride <= 0) {
        CloseHandle(um_mcpt.mapping);
        um_mcpt.mapping = nullptr;
        return false;
    }

    const SIZE_T bytes = static_cast<SIZE_T>(
        UM_MCPT_HEADER + um_mcpt.stride * um_mcpt.slots
    );
    um_mcpt.view = static_cast<const uint8_t *>(
        MapViewOfFile(um_mcpt.mapping, FILE_MAP_READ, 0, 0, bytes)
    );
    if (um_mcpt.view == nullptr) {
        CloseHandle(um_mcpt.mapping);
        um_mcpt.mapping = nullptr;
        return false;
    }
    return true;
}

static bool um_mcpt_create_pipeline() {
    if (um_mcpt.pipelineReady) {
        return true;
    }

    static const char *shader = R"(
Texture2D McWorld : register(t0);
Texture2D McOverlay : register(t1);
SamplerState McSampler : register(s0);

struct VSOut {
    float4 position : SV_POSITION;
    float2 uv : TEXCOORD0;
};

VSOut VSMain(uint id : SV_VertexID) {
    VSOut o;
    float2 uv = float2((id << 1) & 2, id & 2);
    o.position = float4(uv * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0);
    o.uv = uv;
    return o;
}

float4 PSMain(VSOut input) : SV_TARGET {
    // Universal Modder marks its exported Minecraft rows as bottom-up.
    float2 uv = float2(input.uv.x, 1.0 - input.uv.y);
    float4 world = McWorld.Sample(McSampler, uv);
    float4 over = McOverlay.Sample(McSampler, uv);
    // Both layers are premultiplied alpha.
    return over + world * (1.0 - over.a);
}
)";

    ComPtr<ID3DBlob> vsBlob;
    ComPtr<ID3DBlob> psBlob;
    ComPtr<ID3DBlob> errors;
    HRESULT hr = d3d.D3DCompile(
        shader, strlen(shader), "UM MCPT SM64 compositor",
        nullptr, nullptr, "VSMain", "vs_4_0",
        D3DCOMPILE_OPTIMIZATION_LEVEL2, 0,
        vsBlob.GetAddressOf(), errors.GetAddressOf()
    );
    if (FAILED(hr)) return false;

    errors.Reset();
    hr = d3d.D3DCompile(
        shader, strlen(shader), "UM MCPT SM64 compositor",
        nullptr, nullptr, "PSMain", "ps_4_0",
        D3DCOMPILE_OPTIMIZATION_LEVEL2, 0,
        psBlob.GetAddressOf(), errors.GetAddressOf()
    );
    if (FAILED(hr)) return false;

    if (FAILED(d3d.device->CreateVertexShader(
            vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(),
            nullptr, um_mcpt.vs.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreatePixelShader(
            psBlob->GetBufferPointer(), psBlob->GetBufferSize(),
            nullptr, um_mcpt.ps.GetAddressOf()))) return false;

    D3D11_SAMPLER_DESC sd = {};
    sd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    sd.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.MaxLOD = D3D11_FLOAT32_MAX;
    if (FAILED(d3d.device->CreateSamplerState(&sd, um_mcpt.sampler.GetAddressOf())))
        return false;

    D3D11_BLEND_DESC bd = {};
    bd.RenderTarget[0].BlendEnable = TRUE;
    bd.RenderTarget[0].SrcBlend = D3D11_BLEND_ONE;
    bd.RenderTarget[0].DestBlend = D3D11_BLEND_INV_SRC_ALPHA;
    bd.RenderTarget[0].BlendOp = D3D11_BLEND_OP_ADD;
    bd.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;
    bd.RenderTarget[0].DestBlendAlpha = D3D11_BLEND_INV_SRC_ALPHA;
    bd.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;
    bd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
    if (FAILED(d3d.device->CreateBlendState(&bd, um_mcpt.blend.GetAddressOf())))
        return false;

    D3D11_DEPTH_STENCIL_DESC dd = {};
    dd.DepthEnable = FALSE;
    dd.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    dd.DepthFunc = D3D11_COMPARISON_ALWAYS;
    if (FAILED(d3d.device->CreateDepthStencilState(&dd, um_mcpt.noDepth.GetAddressOf())))
        return false;

    D3D11_RASTERIZER_DESC rd = {};
    rd.FillMode = D3D11_FILL_SOLID;
    rd.CullMode = D3D11_CULL_NONE;
    rd.FrontCounterClockwise = TRUE;
    rd.DepthClipEnable = TRUE;
    rd.ScissorEnable = FALSE;
    if (FAILED(d3d.device->CreateRasterizerState(&rd, um_mcpt.raster.GetAddressOf())))
        return false;

    um_mcpt.pipelineReady = true;
    return true;
}

static bool um_mcpt_ensure_textures(uint32_t w, uint32_t h) {
    if (w == um_mcpt.width && h == um_mcpt.height &&
        um_mcpt.worldTexture.Get() != nullptr && um_mcpt.overlayTexture.Get() != nullptr) {
        return true;
    }

    um_mcpt.worldSrv.Reset();
    um_mcpt.overlaySrv.Reset();
    um_mcpt.worldTexture.Reset();
    um_mcpt.overlayTexture.Reset();

    D3D11_TEXTURE2D_DESC td = {};
    td.Width = w;
    td.Height = h;
    td.MipLevels = 1;
    td.ArraySize = 1;
    td.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    td.SampleDesc.Count = 1;
    td.Usage = D3D11_USAGE_DEFAULT;
    td.BindFlags = D3D11_BIND_SHADER_RESOURCE;

    if (FAILED(d3d.device->CreateTexture2D(&td, nullptr, um_mcpt.worldTexture.GetAddressOf())))
        return false;
    if (FAILED(d3d.device->CreateTexture2D(&td, nullptr, um_mcpt.overlayTexture.GetAddressOf())))
        return false;
    if (FAILED(d3d.device->CreateShaderResourceView(
            um_mcpt.worldTexture.Get(), nullptr, um_mcpt.worldSrv.GetAddressOf())))
        return false;
    if (FAILED(d3d.device->CreateShaderResourceView(
            um_mcpt.overlayTexture.Get(), nullptr, um_mcpt.overlaySrv.GetAddressOf())))
        return false;

    um_mcpt.width = w;
    um_mcpt.height = h;
    return true;
}

static void um_mcpt_invalidate_sm64_cache() {
    d3d.last_shader_program = nullptr;
    d3d.last_vertex_buffer_stride = 0;
    d3d.last_blend_state.Reset();
    d3d.last_resource_views[0].Reset();
    d3d.last_resource_views[1].Reset();
    d3d.last_sampler_states[0].Reset();
    d3d.last_sampler_states[1].Reset();
    d3d.last_depth_test = -1;
    d3d.last_depth_mask = -1;
    d3d.last_zmode_decal = -1;
    d3d.last_primitive_topology = D3D_PRIMITIVE_TOPOLOGY_UNDEFINED;
}

static void um_mcpt_draw() {
    if (!um_mcpt_open() || !um_mcpt_create_pipeline()) {
        return;
    }

    const int64_t published = um_mcpt_read<int64_t>(um_mcpt.view + 32);
    const int32_t slot = um_mcpt_read<int32_t>(um_mcpt.view + 40);
    if (slot < 0 || slot >= um_mcpt.slots) {
        return;
    }

    const uint8_t *desc =
        um_mcpt.view + UM_MCPT_SLOT_DESC + UM_MCPT_SLOT_DESC_BYTES * slot;
    const int64_t seq = um_mcpt_read<int64_t>(desc);
    if ((seq & 1) != 0) {
        return;
    }

    const uint32_t w = um_mcpt_read<uint32_t>(desc + 24);
    const uint32_t h = um_mcpt_read<uint32_t>(desc + 28);
    if (w == 0 || h == 0 || w > 3840 || h > 2160) {
        return;
    }

    if (published != um_mcpt.lastPublish) {
        if (!um_mcpt_ensure_textures(w, h)) {
            return;
        }

        const uint8_t *base =
            um_mcpt.view + UM_MCPT_HEADER + um_mcpt.stride * slot;
        const size_t layer = static_cast<size_t>(w) * h * 4;

        d3d.context->UpdateSubresource(
            um_mcpt.worldTexture.Get(), 0, nullptr,
            base, w * 4, 0
        );
        d3d.context->UpdateSubresource(
            um_mcpt.overlayTexture.Get(), 0, nullptr,
            base + 2 * layer, w * 4, 0
        );

        if (um_mcpt_read<int64_t>(desc) != seq) {
            return;
        }
        um_mcpt.lastPublish = published;
    }

    if (um_mcpt.worldSrv.Get() == nullptr || um_mcpt.overlaySrv.Get() == nullptr) {
        return;
    }

    ID3D11ShaderResourceView *srvs[] = {
        um_mcpt.worldSrv.Get(),
        um_mcpt.overlaySrv.Get()
    };
    ID3D11SamplerState *samplers[] = { um_mcpt.sampler.Get() };

    D3D11_VIEWPORT vp = {};
    vp.Width = static_cast<float>(d3d.current_width);
    vp.Height = static_cast<float>(d3d.current_height);
    vp.MinDepth = 0.0f;
    vp.MaxDepth = 1.0f;

    d3d.context->RSSetViewports(1, &vp);
    d3d.context->RSSetState(um_mcpt.raster.Get());
    d3d.context->OMSetRenderTargets(
        1, d3d.backbuffer_view.GetAddressOf(), nullptr
    );
    d3d.context->OMSetBlendState(
        um_mcpt.blend.Get(), nullptr, 0xFFFFFFFF
    );
    d3d.context->OMSetDepthStencilState(um_mcpt.noDepth.Get(), 0);
    d3d.context->IASetInputLayout(nullptr);
    d3d.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    d3d.context->VSSetShader(um_mcpt.vs.Get(), nullptr, 0);
    d3d.context->PSSetShader(um_mcpt.ps.Get(), nullptr, 0);
    d3d.context->PSSetShaderResources(0, 2, srvs);
    d3d.context->PSSetSamplers(0, 1, samplers);
    d3d.context->Draw(3, 0);

    // Do not leave private compositor state hidden behind SM64's own state
    // cache. The next native draw must fully bind its pipeline again.
    ID3D11ShaderResourceView *nullSrvs[] = { nullptr, nullptr };
    d3d.context->PSSetShaderResources(0, 2, nullSrvs);
    um_mcpt_invalidate_sm64_cache();
}
''', encoding="utf-8")

pc_main = PC / "pc_main.c"
patch_once(
    pc_main,
    '#include "configfile.h"\n',
    '#include "configfile.h"\n#include "sm64_passthrough.h"\n',
)
patch_once(
    pc_main,
    "    game_loop_one_iteration();\n",
    "    game_loop_one_iteration();\n"
    "    um_passthrough_frame();\n",
)
patch_once(
    pc_main,
    '    gfx_init(wm_api, rendering_api, "Super Mario 64 PC-Port", configFullscreen);\n',
    '    gfx_init(wm_api, rendering_api, "Super Mario 64 PC-Port", configFullscreen);\n'
    '    um_passthrough_start();\n'
    '    atexit(um_passthrough_stop);\n',
)

gfx_d3d11 = gfx / "gfx_direct3d11.cpp"
patch_once(
    gfx_d3d11,
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n",
    "static LARGE_INTEGER last_time, accumulated_time, frequency;\n"
    "#include \"mcpt_sm64_overlay.inc\"\n",
)
patch_once(
    gfx_d3d11,
    "static void gfx_d3d11_end_frame(void) {\n}\n",
    "static void gfx_d3d11_end_frame(void) {\n"
    "    um_mcpt_draw();\n"
    "}\n",
)

makefile = SM64 / "Makefile"
patch_once(
    makefile,
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -no-pie -mwindows",
    "PLATFORM_LDFLAGS := -lm -lxinput9_1_0 -lole32 -lws2_32 -pthread -no-pie -mwindows",
)

print("Clean SM64 Universal Modder host installed into:", SM64)
print("Transport: Universal Modder ws.cpp/ws.h on 127.0.0.1:25599")
print("Lifecycle: SM64 starts/stops the link and publishes one camera pose per frame")
