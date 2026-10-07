// Direct SM64 D3D11 consumer for Universal Modder's MCPT shared-memory frame.
// The protocol and depth linearization match:
// rehan-remade/universal-modder/examples/minecraft-gta5-passthrough.
//
// Minecraft world is drawn with per-pixel SV_Depth against SM64's existing
// depth buffer. Hand/HUD/screens are then drawn as an independent overlay.

static constexpr wchar_t UM_MCPT_NAME[] = L"Local\\MCPassthroughFrame";
static constexpr uint32_t UM_MCPT_MAGIC = 0x5450434D;
static constexpr size_t UM_MCPT_HEADER = 4096;
static constexpr size_t UM_MCPT_DESC = 256;
static constexpr size_t UM_MCPT_DESC_BYTES = 128;

struct UmMcptState {
    HANDLE mapping = nullptr;
    const uint8_t *memory = nullptr;
    int slots = 0;
    int64_t stride = 0;
    int64_t last_publish = -1;
    DWORD retry_after = 0;

    uint32_t width = 0;
    uint32_t height = 0;
    float mc_near = 0.05f;
    float mc_far = 2048.0f;

    ComPtr<ID3D11Texture2D> world;
    ComPtr<ID3D11Texture2D> depth;
    ComPtr<ID3D11Texture2D> overlay;
    ComPtr<ID3D11ShaderResourceView> world_srv;
    ComPtr<ID3D11ShaderResourceView> depth_srv;
    ComPtr<ID3D11ShaderResourceView> overlay_srv;

    ComPtr<ID3D11VertexShader> vs;
    ComPtr<ID3D11PixelShader> ps_world;
    ComPtr<ID3D11PixelShader> ps_overlay;
    ComPtr<ID3D11SamplerState> sampler_linear;
    ComPtr<ID3D11SamplerState> sampler_point;
    ComPtr<ID3D11BlendState> blend;
    ComPtr<ID3D11DepthStencilState> world_depth;
    ComPtr<ID3D11DepthStencilState> overlay_depth;
    ComPtr<ID3D11Buffer> constants;

    bool pipeline_ready = false;
};

static UmMcptState um_mcpt;

struct UmMcptConstants {
    float mc_near;
    float mc_far;
    float host_near;
    float host_far;
};

template <typename T>
static T um_read(const uint8_t *p) {
    T v;
    std::memcpy(&v, p, sizeof(v));
    return v;
}

static void um_close_mcpt() {
    if (um_mcpt.memory != nullptr) {
        UnmapViewOfFile(um_mcpt.memory);
        um_mcpt.memory = nullptr;
    }
    if (um_mcpt.mapping != nullptr) {
        CloseHandle(um_mcpt.mapping);
        um_mcpt.mapping = nullptr;
    }
    um_mcpt.slots = 0;
    um_mcpt.stride = 0;
    um_mcpt.last_publish = -1;
}

static bool um_open_mcpt() {
    if (um_mcpt.memory != nullptr) return true;

    const DWORD now = GetTickCount();
    if (now < um_mcpt.retry_after) return false;
    um_mcpt.retry_after = now + 1000;

    HANDLE mapping = OpenFileMappingW(
        FILE_MAP_READ, FALSE, UM_MCPT_NAME
    );
    if (mapping == nullptr) return false;

    const uint8_t *header = static_cast<const uint8_t *>(
        MapViewOfFile(
            mapping, FILE_MAP_READ, 0, 0, UM_MCPT_HEADER
        )
    );
    if (header == nullptr
        || um_read<uint32_t>(header) != UM_MCPT_MAGIC) {
        if (header != nullptr) UnmapViewOfFile(header);
        CloseHandle(mapping);
        return false;
    }

    const int slots = um_read<int32_t>(header + 12);
    const int64_t stride = um_read<int64_t>(header + 16);
    UnmapViewOfFile(header);

    if (slots <= 0 || slots > 8 || stride <= 0) {
        CloseHandle(mapping);
        return false;
    }

    const SIZE_T bytes = static_cast<SIZE_T>(
        UM_MCPT_HEADER + stride * slots
    );
    const uint8_t *memory = static_cast<const uint8_t *>(
        MapViewOfFile(
            mapping, FILE_MAP_READ, 0, 0, bytes
        )
    );
    if (memory == nullptr) {
        CloseHandle(mapping);
        return false;
    }

    um_mcpt.mapping = mapping;
    um_mcpt.memory = memory;
    um_mcpt.slots = slots;
    um_mcpt.stride = stride;
    return true;
}

static void um_reset_textures() {
    um_mcpt.world_srv.Reset();
    um_mcpt.depth_srv.Reset();
    um_mcpt.overlay_srv.Reset();
    um_mcpt.world.Reset();
    um_mcpt.depth.Reset();
    um_mcpt.overlay.Reset();
    um_mcpt.width = 0;
    um_mcpt.height = 0;
}

static bool um_create_rgba(
    uint32_t w,
    uint32_t h,
    ComPtr<ID3D11Texture2D> &texture,
    ComPtr<ID3D11ShaderResourceView> &srv
) {
    D3D11_TEXTURE2D_DESC td = {};
    td.Width = w;
    td.Height = h;
    td.MipLevels = 1;
    td.ArraySize = 1;
    td.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    td.SampleDesc.Count = 1;
    td.Usage = D3D11_USAGE_DEFAULT;
    td.BindFlags = D3D11_BIND_SHADER_RESOURCE;

    if (FAILED(d3d.device->CreateTexture2D(
        &td, nullptr, texture.GetAddressOf()
    ))) return false;

    return SUCCEEDED(d3d.device->CreateShaderResourceView(
        texture.Get(), nullptr, srv.GetAddressOf()
    ));
}

static bool um_create_depth(
    uint32_t w,
    uint32_t h,
    ComPtr<ID3D11Texture2D> &texture,
    ComPtr<ID3D11ShaderResourceView> &srv
) {
    D3D11_TEXTURE2D_DESC td = {};
    td.Width = w;
    td.Height = h;
    td.MipLevels = 1;
    td.ArraySize = 1;
    td.Format = DXGI_FORMAT_R32_FLOAT;
    td.SampleDesc.Count = 1;
    td.Usage = D3D11_USAGE_DEFAULT;
    td.BindFlags = D3D11_BIND_SHADER_RESOURCE;

    if (FAILED(d3d.device->CreateTexture2D(
        &td, nullptr, texture.GetAddressOf()
    ))) return false;

    return SUCCEEDED(d3d.device->CreateShaderResourceView(
        texture.Get(), nullptr, srv.GetAddressOf()
    ));
}

static bool um_ensure_textures(uint32_t w, uint32_t h) {
    if (um_mcpt.width == w
        && um_mcpt.height == h
        && um_mcpt.world.Get() != nullptr
        && um_mcpt.depth.Get() != nullptr
        && um_mcpt.overlay.Get() != nullptr) {
        return true;
    }

    um_reset_textures();

    if (!um_create_rgba(
            w, h, um_mcpt.world, um_mcpt.world_srv)
        || !um_create_depth(
            w, h, um_mcpt.depth, um_mcpt.depth_srv)
        || !um_create_rgba(
            w, h, um_mcpt.overlay, um_mcpt.overlay_srv)) {
        um_reset_textures();
        return false;
    }

    um_mcpt.width = w;
    um_mcpt.height = h;
    return true;
}

static bool um_create_pipeline() {
    if (um_mcpt.pipeline_ready) return true;

    static const char *shader = R"(
Texture2D WorldTex   : register(t0);
Texture2D McDepthTex : register(t1);
Texture2D OverlayTex : register(t2);

SamplerState LinearSampler : register(s0);
SamplerState PointSampler  : register(s1);

cbuffer Planes : register(b0) {
    float McNear;
    float McFar;
    float HostNear;
    float HostFar;
};

struct VSOut {
    float4 position : SV_POSITION;
    float2 uv : TEXCOORD0;
};

VSOut VSMain(uint id : SV_VertexID) {
    VSOut o;
    float2 uv = float2((id << 1) & 2, id & 2);
    o.position = float4(
        uv * float2(2.0, -2.0) + float2(-1.0, 1.0),
        0.0,
        1.0
    );
    o.uv = uv;
    return o;
}

float mc_linear(float d) {
    if (d <= 0.0) return 1e9;
    return McNear * McFar
        / (McNear + d * (McFar - McNear));
}

float host_depth(float z) {
    z = max(z, HostNear + 0.001);
    return saturate(
        HostFar / (HostFar - HostNear)
        - (HostNear * HostFar)
          / ((HostFar - HostNear) * z)
    );
}

struct WorldOut {
    float4 color : SV_TARGET;
    float depth : SV_DEPTH;
};

WorldOut PSWorld(VSOut i) {
    float2 uv = float2(i.uv.x, 1.0 - i.uv.y);
    float4 world = WorldTex.Sample(LinearSampler, uv);
    if (world.a <= 0.001) discard;

    float d = McDepthTex.SampleLevel(
        PointSampler, uv, 0.0
    ).r;
    float z = mc_linear(d);
    if (z >= 1e8 || z > HostFar) discard;

    WorldOut o;
    o.color = world;
    o.depth = host_depth(z);
    return o;
}

float4 PSOverlay(VSOut i) : SV_TARGET {
    float2 uv = float2(i.uv.x, 1.0 - i.uv.y);
    return OverlayTex.Sample(LinearSampler, uv);
}
)";

    ComPtr<ID3DBlob> vs_blob;
    ComPtr<ID3DBlob> world_blob;
    ComPtr<ID3DBlob> overlay_blob;
    ComPtr<ID3DBlob> errors;

    const UINT flags = D3DCOMPILE_OPTIMIZATION_LEVEL2;

    if (FAILED(d3d.D3DCompile(
        shader,
        std::strlen(shader),
        "UniversalModderSM64",
        nullptr,
        nullptr,
        "VSMain",
        "vs_4_0_level_9_1",
        flags,
        0,
        vs_blob.GetAddressOf(),
        errors.GetAddressOf()
    ))) return false;

    errors.Reset();
    if (FAILED(d3d.D3DCompile(
        shader,
        std::strlen(shader),
        "UniversalModderSM64",
        nullptr,
        nullptr,
        "PSWorld",
        "ps_4_0_level_9_1",
        flags,
        0,
        world_blob.GetAddressOf(),
        errors.GetAddressOf()
    ))) return false;

    errors.Reset();
    if (FAILED(d3d.D3DCompile(
        shader,
        std::strlen(shader),
        "UniversalModderSM64",
        nullptr,
        nullptr,
        "PSOverlay",
        "ps_4_0_level_9_1",
        flags,
        0,
        overlay_blob.GetAddressOf(),
        errors.GetAddressOf()
    ))) return false;

    if (FAILED(d3d.device->CreateVertexShader(
        vs_blob->GetBufferPointer(),
        vs_blob->GetBufferSize(),
        nullptr,
        um_mcpt.vs.GetAddressOf()
    ))) return false;

    if (FAILED(d3d.device->CreatePixelShader(
        world_blob->GetBufferPointer(),
        world_blob->GetBufferSize(),
        nullptr,
        um_mcpt.ps_world.GetAddressOf()
    ))) return false;

    if (FAILED(d3d.device->CreatePixelShader(
        overlay_blob->GetBufferPointer(),
        overlay_blob->GetBufferSize(),
        nullptr,
        um_mcpt.ps_overlay.GetAddressOf()
    ))) return false;

    D3D11_SAMPLER_DESC linear = {};
    linear.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    linear.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
    linear.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
    linear.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    linear.MaxLOD = D3D11_FLOAT32_MAX;
    if (FAILED(d3d.device->CreateSamplerState(
        &linear, um_mcpt.sampler_linear.GetAddressOf()
    ))) return false;

    D3D11_SAMPLER_DESC point = linear;
    point.Filter = D3D11_FILTER_MIN_MAG_MIP_POINT;
    if (FAILED(d3d.device->CreateSamplerState(
        &point, um_mcpt.sampler_point.GetAddressOf()
    ))) return false;

    D3D11_BLEND_DESC blend = {};
    blend.RenderTarget[0].BlendEnable = TRUE;
    blend.RenderTarget[0].SrcBlend = D3D11_BLEND_ONE;
    blend.RenderTarget[0].DestBlend = D3D11_BLEND_INV_SRC_ALPHA;
    blend.RenderTarget[0].BlendOp = D3D11_BLEND_OP_ADD;
    blend.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;
    blend.RenderTarget[0].DestBlendAlpha =
        D3D11_BLEND_INV_SRC_ALPHA;
    blend.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;
    blend.RenderTarget[0].RenderTargetWriteMask =
        D3D11_COLOR_WRITE_ENABLE_ALL;

    if (FAILED(d3d.device->CreateBlendState(
        &blend, um_mcpt.blend.GetAddressOf()
    ))) return false;

    D3D11_DEPTH_STENCIL_DESC world_depth = {};
    world_depth.DepthEnable = TRUE;
    world_depth.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    world_depth.DepthFunc = D3D11_COMPARISON_LESS_EQUAL;
    if (FAILED(d3d.device->CreateDepthStencilState(
        &world_depth,
        um_mcpt.world_depth.GetAddressOf()
    ))) return false;

    D3D11_DEPTH_STENCIL_DESC overlay_depth = {};
    overlay_depth.DepthEnable = FALSE;
    overlay_depth.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    overlay_depth.DepthFunc = D3D11_COMPARISON_ALWAYS;
    if (FAILED(d3d.device->CreateDepthStencilState(
        &overlay_depth,
        um_mcpt.overlay_depth.GetAddressOf()
    ))) return false;

    D3D11_BUFFER_DESC cb = {};
    cb.ByteWidth = sizeof(UmMcptConstants);
    cb.Usage = D3D11_USAGE_DYNAMIC;
    cb.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    cb.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;

    if (FAILED(d3d.device->CreateBuffer(
        &cb, nullptr, um_mcpt.constants.GetAddressOf()
    ))) return false;

    um_mcpt.pipeline_ready = true;
    return true;
}

static bool um_upload_latest() {
    if (!um_open_mcpt()) return false;

    const int64_t published =
        um_read<int64_t>(um_mcpt.memory + 32);
    const int32_t slot =
        um_read<int32_t>(um_mcpt.memory + 40);

    if (slot < 0 || slot >= um_mcpt.slots) return false;

    const uint8_t *desc =
        um_mcpt.memory + UM_MCPT_DESC
        + UM_MCPT_DESC_BYTES * slot;

    const int64_t seq = um_read<int64_t>(desc);
    if (seq & 1) return false;

    const uint32_t w = um_read<uint32_t>(desc + 24);
    const uint32_t h = um_read<uint32_t>(desc + 28);

    if (w == 0 || h == 0 || w > 3840 || h > 2160) {
        return false;
    }

    if (published == um_mcpt.last_publish
        && um_mcpt.width == w
        && um_mcpt.height == h) {
        return true;
    }

    if (!um_ensure_textures(w, h)) return false;

    const uint8_t *base =
        um_mcpt.memory + UM_MCPT_HEADER
        + um_mcpt.stride * slot;
    const size_t layer = static_cast<size_t>(w) * h * 4;

    d3d.context->UpdateSubresource(
        um_mcpt.world.Get(),
        0,
        nullptr,
        base,
        w * 4,
        0
    );
    d3d.context->UpdateSubresource(
        um_mcpt.depth.Get(),
        0,
        nullptr,
        base + layer,
        w * 4,
        0
    );
    d3d.context->UpdateSubresource(
        um_mcpt.overlay.Get(),
        0,
        nullptr,
        base + 2 * layer,
        w * 4,
        0
    );

    if (um_read<int64_t>(desc) != seq) return false;

    um_mcpt.mc_near = um_read<float>(desc + 32);
    um_mcpt.mc_far = um_read<float>(desc + 36);
    um_mcpt.last_publish = published;
    return true;
}

static void um_invalidate_sm64_state() {
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
    d3d.last_primitive_topology =
        D3D_PRIMITIVE_TOPOLOGY_UNDEFINED;
}

static void um_bind_common() {
    D3D11_VIEWPORT vp = {};
    vp.Width = static_cast<float>(d3d.current_width);
    vp.Height = static_cast<float>(d3d.current_height);
    vp.MinDepth = 0.0f;
    vp.MaxDepth = 1.0f;
    d3d.context->RSSetViewports(1, &vp);

    d3d.context->IASetInputLayout(nullptr);
    d3d.context->IASetPrimitiveTopology(
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST
    );
    d3d.context->VSSetShader(um_mcpt.vs.Get(), nullptr, 0);

    ID3D11ShaderResourceView *views[] = {
        um_mcpt.world_srv.Get(),
        um_mcpt.depth_srv.Get(),
        um_mcpt.overlay_srv.Get()
    };
    d3d.context->PSSetShaderResources(0, 3, views);

    ID3D11SamplerState *samplers[] = {
        um_mcpt.sampler_linear.Get(),
        um_mcpt.sampler_point.Get()
    };
    d3d.context->PSSetSamplers(0, 2, samplers);

    UmMcptConstants planes = {
        um_mcpt.mc_near,
        um_mcpt.mc_far,
        1.0f,
        300.0f
    };

    D3D11_MAPPED_SUBRESOURCE mapped = {};
    if (SUCCEEDED(d3d.context->Map(
        um_mcpt.constants.Get(),
        0,
        D3D11_MAP_WRITE_DISCARD,
        0,
        &mapped
    ))) {
        std::memcpy(
            mapped.pData,
            &planes,
            sizeof(planes)
        );
        d3d.context->Unmap(um_mcpt.constants.Get(), 0);
    }

    ID3D11Buffer *cb[] = { um_mcpt.constants.Get() };
    d3d.context->PSSetConstantBuffers(0, 1, cb);

    d3d.context->OMSetBlendState(
        um_mcpt.blend.Get(),
        nullptr,
        0xFFFFFFFF
    );
}

static void um_draw_mcpt() {
    if (!um_passthrough_connected()) return;
    if (!um_create_pipeline()) return;
    if (!um_upload_latest()) return;

    um_bind_common();

    // Pass 1: real Minecraft world against SM64's actual depth buffer.
    d3d.context->OMSetRenderTargets(
        1,
        d3d.backbuffer_view.GetAddressOf(),
        d3d.depth_stencil_view.Get()
    );
    d3d.context->OMSetDepthStencilState(
        um_mcpt.world_depth.Get(),
        0
    );
    d3d.context->PSSetShader(
        um_mcpt.ps_world.Get(),
        nullptr,
        0
    );
    d3d.context->Draw(3, 0);

    // Pass 2: Minecraft hand, HUD, inventory and screens always on top.
    d3d.context->OMSetRenderTargets(
        1,
        d3d.backbuffer_view.GetAddressOf(),
        nullptr
    );
    d3d.context->OMSetDepthStencilState(
        um_mcpt.overlay_depth.Get(),
        0
    );
    d3d.context->PSSetShader(
        um_mcpt.ps_overlay.Get(),
        nullptr,
        0
    );
    d3d.context->Draw(3, 0);

    ID3D11ShaderResourceView *null_views[] = {
        nullptr, nullptr, nullptr
    };
    d3d.context->PSSetShaderResources(
        0, 3, null_views
    );

    um_invalidate_sm64_state();
}
