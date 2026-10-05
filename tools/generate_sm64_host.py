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
#include <string>
#include <unordered_set>

extern "C" {
#include "engine/surface_collision.h"
#include "game/area.h"
#include "game/camera.h"
#include "game/level_update.h"
#include "game/mario.h"
extern struct CameraFOVStatus sFOVState;
}

static WsClient s_ws;
static unsigned long long s_frame = 0;
static int s_generation = -1;
static int s_level = -1;
static int s_area = -1;
static std::unordered_set<unsigned long long> s_groundSampled;

static unsigned long long column_key(int x, int z) {
    return (static_cast<unsigned long long>(static_cast<unsigned int>(x)) << 32)
        | static_cast<unsigned int>(z);
}

static void reset_ground_if_needed() {
    const int generation = s_ws.generation();
    if (generation == s_generation
        && gCurrLevelNum == s_level
        && gCurrAreaIndex == s_area) {
        return;
    }

    s_generation = generation;
    s_level = gCurrLevelNum;
    s_area = gCurrAreaIndex;
    s_groundSampled.clear();
    s_ws.send("{\"t\":\"clear\"}");
}

static void sample_ground(float playerX, float playerZ) {
    constexpr float SCALE = 100.0f;
    constexpr float MC_Y_ORIGIN = 64.0f;
    constexpr int RADIUS = 12;
    constexpr int DEPTH = 2;
    constexpr int BUDGET = 80;

    const int centerX = static_cast<int>(std::floor(playerX));
    const int centerZ = static_cast<int>(std::floor(playerZ));
    int probes = 0;
    std::string columns;

    for (int dz = -RADIUS; dz <= RADIUS && probes < BUDGET; ++dz) {
        for (int dx = -RADIUS; dx <= RADIUS && probes < BUDGET; ++dx) {
            if (dx * dx + dz * dz > RADIUS * RADIUS) {
                continue;
            }

            const int x = centerX + dx;
            const int z = centerZ + dz;
            const auto key = column_key(x, z);
            if (s_groundSampled.count(key) != 0) {
                continue;
            }

            ++probes;
            const float sm64X = (x + 0.5f) * SCALE;
            const float sm64Z = -(z + 0.5f) * SCALE;
            struct Surface *floorSurface = nullptr;
            const float floorY = find_floor(
                sm64X,
                gMarioState->pos[1] + 200.0f,
                sm64Z,
                &floorSurface
            );

            if (floorSurface == nullptr) {
                continue;
            }

            s_groundSampled.insert(key);
            const float mcFloorY = floorY / SCALE + MC_Y_ORIGIN;
            const int top = static_cast<int>(std::floor(mcFloorY + 0.5f)) - 1;
            char entry[80];
            std::snprintf(
                entry,
                sizeof(entry),
                "%s%d,%d,%d,%d",
                columns.empty() ? "" : ",",
                x, z, top - DEPTH + 1, top
            );
            columns += entry;
        }
    }

    if (!columns.empty()) {
        s_ws.send("{\"t\":\"ground\",\"c\":[" + columns + "]}");
    }
}

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
    const float renderFov = sFOVState.fov + sFOVState.fovOffset;

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
        "\"fov\":%.3f,\"fp\":false,"
        "\"pl\":[%.4f,%.4f,%.4f],\"h\":%.3f}",
        ++s_frame,
        cameraX, cameraY, cameraZ,
        cameraYaw, cameraPitch, renderFov,
        playerX, playerY, playerZ,
        bodyYaw
    );
    s_ws.send(message);
    reset_ground_if_needed();
    sample_ground(playerX, playerZ);
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
    ComPtr<ID3D11Texture2D> depthTexture;
    ComPtr<ID3D11Texture2D> overlayTexture;
    ComPtr<ID3D11ShaderResourceView> worldSrv;
    ComPtr<ID3D11ShaderResourceView> depthSrv;
    ComPtr<ID3D11ShaderResourceView> overlaySrv;

    ComPtr<ID3D11VertexShader> vs;
    ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11SamplerState> sampler;
    ComPtr<ID3D11SamplerState> depthSampler;
    ComPtr<ID3D11Buffer> depthConstants;
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
Texture2D<float> McDepth : register(t2);
Texture2D<float> HostDepth : register(t3);
SamplerState McSampler : register(s0);
SamplerState DepthSampler : register(s1);

cbuffer UmDepthParams : register(b2) {
    float McNear;
    float McFar;
    float HostNear;
    float HostFar;
    float DepthBias;
    float3 DepthPadding;
};

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

float mc_linear(float d) {
    if (d <= 0.0) return 1e9;
    return McNear * McFar / (McNear + d * (McFar - McNear));
}

float host_linear(float d) {
    if (d >= 1.0) return HostFar;
    return HostNear * HostFar / (HostFar - d * (HostFar - HostNear));
}

float4 PSMain(VSOut input) : SV_TARGET {
    float2 mcUv = float2(input.uv.x, 1.0 - input.uv.y);
    float4 world = McWorld.Sample(McSampler, mcUv);
    float4 over = McOverlay.Sample(McSampler, mcUv);

    float mcZ = mc_linear(McDepth.SampleLevel(DepthSampler, mcUv, 0));
    float hostZ = host_linear(HostDepth.SampleLevel(DepthSampler, input.uv, 0));
    float visible = mcZ < hostZ + DepthBias ? 1.0 : 0.0;
    world *= visible;

    // World obeys host depth. Hand/HUD/screens always stay on top.
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

    D3D11_SAMPLER_DESC depthSd = sd;
    depthSd.Filter = D3D11_FILTER_MIN_MAG_MIP_POINT;
    if (FAILED(d3d.device->CreateSamplerState(&depthSd, um_mcpt.depthSampler.GetAddressOf())))
        return false;

    D3D11_BUFFER_DESC cbd = {};
    cbd.ByteWidth = 32;
    cbd.Usage = D3D11_USAGE_DYNAMIC;
    cbd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    cbd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    if (FAILED(d3d.device->CreateBuffer(&cbd, nullptr, um_mcpt.depthConstants.GetAddressOf())))
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
        um_mcpt.worldTexture.Get() != nullptr &&
        um_mcpt.depthTexture.Get() != nullptr &&
        um_mcpt.overlayTexture.Get() != nullptr) {
        return true;
    }

    um_mcpt.worldSrv.Reset();
    um_mcpt.depthSrv.Reset();
    um_mcpt.overlaySrv.Reset();
    um_mcpt.worldTexture.Reset();
    um_mcpt.depthTexture.Reset();
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

    td.Format = DXGI_FORMAT_R32_FLOAT;
    if (FAILED(d3d.device->CreateTexture2D(&td, nullptr, um_mcpt.depthTexture.GetAddressOf())))
        return false;
    if (FAILED(d3d.device->CreateShaderResourceView(
            um_mcpt.depthTexture.Get(), nullptr, um_mcpt.depthSrv.GetAddressOf())))
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
            um_mcpt.depthTexture.Get(), 0, nullptr,
            base + layer, w * 4, 0
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

    if (um_mcpt.worldSrv.Get() == nullptr
        || um_mcpt.depthSrv.Get() == nullptr
        || um_mcpt.overlaySrv.Get() == nullptr
        || d3d.depth_stencil_srv.Get() == nullptr) {
        return;
    }

    struct DepthParams {
        float mcNear, mcFar, hostNear, hostFar;
        float depthBias, pad0, pad1, pad2;
    } params = {
        um_mcpt_read<float>(desc + 32),
        um_mcpt_read<float>(desc + 36),
        1.0f, 300.0f,
        0.05f, 0.0f, 0.0f, 0.0f
    };
    D3D11_MAPPED_SUBRESOURCE cbMap = {};
    if (FAILED(d3d.context->Map(
            um_mcpt.depthConstants.Get(), 0,
            D3D11_MAP_WRITE_DISCARD, 0, &cbMap))) {
        return;
    }
    memcpy(cbMap.pData, &params, sizeof(params));
    d3d.context->Unmap(um_mcpt.depthConstants.Get(), 0);

    ID3D11ShaderResourceView *srvs[] = {
        um_mcpt.worldSrv.Get(),
        um_mcpt.overlaySrv.Get(),
        um_mcpt.depthSrv.Get(),
        d3d.depth_stencil_srv.Get()
    };
    ID3D11SamplerState *samplers[] = {
        um_mcpt.sampler.Get(),
        um_mcpt.depthSampler.Get()
    };

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
    d3d.context->PSSetShaderResources(0, 4, srvs);
    d3d.context->PSSetSamplers(0, 2, samplers);
    d3d.context->PSSetConstantBuffers(2, 1, um_mcpt.depthConstants.GetAddressOf());
    d3d.context->Draw(3, 0);

    // Do not leave private compositor state hidden behind SM64's own state
    // cache. The next native draw must fully bind its pipeline again.
    ID3D11ShaderResourceView *nullSrvs[] = { nullptr, nullptr, nullptr, nullptr };
    d3d.context->PSSetShaderResources(0, 4, nullSrvs);
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
    "#include <cstdio>\n",
    "#include <cstdio>\n#include <cstring>\n",
)
patch_once(
    gfx_d3d11,
    "    ComPtr<ID3D11DepthStencilView> depth_stencil_view;\n",
    "    ComPtr<ID3D11DepthStencilView> depth_stencil_view;\n"
    "    ComPtr<ID3D11Texture2D> depth_stencil_texture;\n"
    "    ComPtr<ID3D11ShaderResourceView> depth_stencil_srv;\n",
)
patch_once(
    gfx_d3d11,
    "        d3d.depth_stencil_view.Reset();\n",
    "        d3d.depth_stencil_view.Reset();\n"
    "        d3d.depth_stencil_srv.Reset();\n"
    "        d3d.depth_stencil_texture.Reset();\n",
)
patch_once(
    gfx_d3d11,
    "    depth_stencil_texture_desc.Format = d3d.feature_level >= D3D_FEATURE_LEVEL_10_0 ?\n                                        DXGI_FORMAT_D32_FLOAT : DXGI_FORMAT_D24_UNORM_S8_UINT;\n    depth_stencil_texture_desc.SampleDesc = d3d.sample_description;\n    depth_stencil_texture_desc.Usage = D3D11_USAGE_DEFAULT;\n    depth_stencil_texture_desc.BindFlags = D3D11_BIND_DEPTH_STENCIL;\n    depth_stencil_texture_desc.CPUAccessFlags = 0;\n    depth_stencil_texture_desc.MiscFlags = 0;\n\n    ComPtr<ID3D11Texture2D> depth_stencil_texture;\n    ThrowIfFailed(d3d.device->CreateTexture2D(&depth_stencil_texture_desc, nullptr, depth_stencil_texture.GetAddressOf()));\n    ThrowIfFailed(d3d.device->CreateDepthStencilView(depth_stencil_texture.Get(), nullptr, d3d.depth_stencil_view.GetAddressOf()));",
    "    const bool depth32 = d3d.feature_level >= D3D_FEATURE_LEVEL_10_0;\n    depth_stencil_texture_desc.Format = depth32 ?\n        DXGI_FORMAT_R32_TYPELESS : DXGI_FORMAT_R24G8_TYPELESS;\n    depth_stencil_texture_desc.SampleDesc = d3d.sample_description;\n    depth_stencil_texture_desc.Usage = D3D11_USAGE_DEFAULT;\n    depth_stencil_texture_desc.BindFlags =\n        D3D11_BIND_DEPTH_STENCIL | D3D11_BIND_SHADER_RESOURCE;\n    depth_stencil_texture_desc.CPUAccessFlags = 0;\n    depth_stencil_texture_desc.MiscFlags = 0;\n\n    ThrowIfFailed(d3d.device->CreateTexture2D(\n        &depth_stencil_texture_desc, nullptr,\n        d3d.depth_stencil_texture.GetAddressOf()));\n\n    D3D11_DEPTH_STENCIL_VIEW_DESC dsv_desc = {};\n    dsv_desc.Format = depth32 ?\n        DXGI_FORMAT_D32_FLOAT : DXGI_FORMAT_D24_UNORM_S8_UINT;\n    dsv_desc.ViewDimension = D3D11_DSV_DIMENSION_TEXTURE2D;\n    ThrowIfFailed(d3d.device->CreateDepthStencilView(\n        d3d.depth_stencil_texture.Get(), &dsv_desc,\n        d3d.depth_stencil_view.GetAddressOf()));\n\n    D3D11_SHADER_RESOURCE_VIEW_DESC srv_desc = {};\n    srv_desc.Format = depth32 ?\n        DXGI_FORMAT_R32_FLOAT : DXGI_FORMAT_R24_UNORM_X8_TYPELESS;\n    srv_desc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;\n    srv_desc.Texture2D.MipLevels = 1;\n    ThrowIfFailed(d3d.device->CreateShaderResourceView(\n        d3d.depth_stencil_texture.Get(), &srv_desc,\n        d3d.depth_stencil_srv.GetAddressOf()));",
)
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
