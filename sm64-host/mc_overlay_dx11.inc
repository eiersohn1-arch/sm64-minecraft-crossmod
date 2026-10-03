/*
 * Minecraft -> SM64 D3D11 compositor.
 *
 * This file is copied into sm64-port/src/pc/gfx and included directly by
 * gfx_direct3d11.cpp after the private d3d state is declared. Keeping it as an
 * .inc lets the crossmod use the port's existing D3D11 device/backbuffer
 * without changing any public SM64 renderer interfaces.
 */

#define MC_OVERLAY_MAGIC 0x58343653u
#define MC_OVERLAY_VERSION 1u
#define MC_OVERLAY_HEADER 4096u
#define MC_OVERLAY_MAX_WIDTH 3840u
#define MC_OVERLAY_MAX_HEIGHT 2160u
#define MC_OVERLAY_MAX_PIXELS ((uint64_t) MC_OVERLAY_MAX_WIDTH * MC_OVERLAY_MAX_HEIGHT)
#define MC_OVERLAY_FILE_BYTES ((uint64_t) MC_OVERLAY_HEADER + MC_OVERLAY_MAX_PIXELS * 12ull)

struct McOverlayVertex {
    float x;
    float y;
    float u;
    float v;
};

struct McOverlayConstants {
    float mc_near;
    float mc_far;
    float host_near;
    float host_far;
    float mc_aspect;
    float host_aspect;
    float depth_bias;
    float padding;
};

static struct {
    HANDLE file = INVALID_HANDLE_VALUE;
    HANDLE mapping = nullptr;
    const uint8_t *view = nullptr;
    DWORD next_open_attempt = 0;

    uint64_t last_sequence = 0;
    uint32_t width = 0;
    uint32_t height = 0;

    ComPtr<ID3D11Texture2D> world_texture;
    ComPtr<ID3D11Texture2D> mc_depth_texture;
    ComPtr<ID3D11Texture2D> overlay_texture;

    ComPtr<ID3D11ShaderResourceView> world_srv;
    ComPtr<ID3D11ShaderResourceView> mc_depth_srv;
    ComPtr<ID3D11ShaderResourceView> overlay_srv;

    ComPtr<ID3D11VertexShader> vertex_shader;
    ComPtr<ID3D11PixelShader> pixel_shader;
    ComPtr<ID3D11InputLayout> input_layout;
    ComPtr<ID3D11Buffer> vertex_buffer;
    ComPtr<ID3D11Buffer> constant_buffer;
    ComPtr<ID3D11SamplerState> linear_sampler;
    ComPtr<ID3D11SamplerState> point_sampler;
    ComPtr<ID3D11BlendState> blend_state;
    ComPtr<ID3D11DepthStencilState> depth_state;
    ComPtr<ID3D11RasterizerState> rasterizer_state;

    bool initialized = false;
    bool shader_failed = false;
} mc_overlay;

template <typename T>
static T mc_overlay_read(size_t offset) {
    T value;
    memcpy(&value, mc_overlay.view + offset, sizeof(T));
    return value;
}

static void mc_overlay_close_mapping(void) {
    if (mc_overlay.view != nullptr) {
        UnmapViewOfFile(mc_overlay.view);
        mc_overlay.view = nullptr;
    }
    if (mc_overlay.mapping != nullptr) {
        CloseHandle(mc_overlay.mapping);
        mc_overlay.mapping = nullptr;
    }
    if (mc_overlay.file != INVALID_HANDLE_VALUE) {
        CloseHandle(mc_overlay.file);
        mc_overlay.file = INVALID_HANDLE_VALUE;
    }
}

static bool mc_overlay_open_mapping(void) {
    if (mc_overlay.view != nullptr) {
        return true;
    }

    DWORD now = GetTickCount();
    if (now < mc_overlay.next_open_attempt) {
        return false;
    }
    mc_overlay.next_open_attempt = now + 500;

    wchar_t path[MAX_PATH];
    DWORD length = GetTempPathW(MAX_PATH, path);
    if (length == 0 || length >= MAX_PATH - 32) {
        return false;
    }
    lstrcatW(path, L"sm64cross_frame.bin");

    mc_overlay.file = CreateFileW(
        path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        nullptr
    );
    if (mc_overlay.file == INVALID_HANDLE_VALUE) {
        return false;
    }

    LARGE_INTEGER size;
    if (!GetFileSizeEx(mc_overlay.file, &size)
            || (uint64_t) size.QuadPart < MC_OVERLAY_FILE_BYTES) {
        mc_overlay_close_mapping();
        return false;
    }

    mc_overlay.mapping = CreateFileMappingW(
        mc_overlay.file,
        nullptr,
        PAGE_READONLY,
        0,
        0,
        nullptr
    );
    if (mc_overlay.mapping == nullptr) {
        mc_overlay_close_mapping();
        return false;
    }

    mc_overlay.view = static_cast<const uint8_t *>(
        MapViewOfFile(
            mc_overlay.mapping,
            FILE_MAP_READ,
            0,
            0,
            0
        )
    );
    if (mc_overlay.view == nullptr) {
        mc_overlay_close_mapping();
        return false;
    }

    if (mc_overlay_read<uint32_t>(0) != MC_OVERLAY_MAGIC
            || mc_overlay_read<uint32_t>(4) != MC_OVERLAY_VERSION) {
        mc_overlay_close_mapping();
        return false;
    }

    return true;
}

static bool mc_overlay_compile_shader(
        const char *source,
        const char *entry,
        const char *profile,
        ComPtr<ID3DBlob> &blob
) {
    ComPtr<ID3DBlob> error_blob;
    HRESULT hr = d3d.D3DCompile(
        source,
        strlen(source),
        "sm64cross_compositor",
        nullptr,
        nullptr,
        entry,
        profile,
        D3DCOMPILE_OPTIMIZATION_LEVEL2,
        0,
        blob.GetAddressOf(),
        error_blob.GetAddressOf()
    );

    if (FAILED(hr)) {
        if (error_blob.Get() != nullptr) {
            MessageBoxA(
                gfx_dxgi_get_h_wnd(),
                static_cast<const char *>(error_blob->GetBufferPointer()),
                "SM64 x Minecraft compositor shader error",
                MB_OK | MB_ICONERROR
            );
        }
        return false;
    }

    return true;
}

static bool mc_overlay_init_pipeline(void) {
    if (mc_overlay.initialized) {
        return true;
    }
    if (mc_overlay.shader_failed) {
        return false;
    }

    static const char *shader_source = R"HLSL(
struct VSInput {
    float2 pos : POSITION;
    float2 uv : TEXCOORD0;
};

struct VSOutput {
    float4 pos : SV_POSITION;
    float2 uv : TEXCOORD0;
};

VSOutput VSMain(VSInput input) {
    VSOutput output;
    output.pos = float4(input.pos, 0.0, 1.0);
    output.uv = input.uv;
    return output;
}

Texture2D McWorld : register(t0);
Texture2D McDepth : register(t1);
Texture2D McOverlay : register(t2);
Texture2D HostDepth : register(t3);

SamplerState LinearSampler : register(s0);
SamplerState PointSampler : register(s1);

cbuffer OverlayConstants : register(b0) {
    float McNear;
    float McFar;
    float HostNear;
    float HostFar;
    float McAspect;
    float HostAspect;
    float DepthBias;
    float Padding;
};

float linear_depth(float d, float n, float f) {
    if (d >= 0.999999) {
        return 1.0e20;
    }
    return (n * f) / max(f - d * (f - n), 1.0e-6);
}

float4 PSMain(VSOutput input) : SV_TARGET {
    /*
     * Minecraft's glGetTexImage rows are bottom-up. The X correction keeps
     * the same vertical FOV even if the hidden Minecraft window and visible
     * SM64 window use different aspect ratios.
     */
    float ndc_x = input.uv.x * 2.0 - 1.0;
    float mc_ndc_x = ndc_x * HostAspect / max(McAspect, 1.0e-6);
    float2 mc_uv = float2(
        mc_ndc_x * 0.5 + 0.5,
        1.0 - input.uv.y
    );

    bool inside = all(mc_uv >= 0.0) && all(mc_uv <= 1.0);

    float4 world = 0.0;
    float4 overlay = 0.0;
    float mc_d = 1.0;

    if (inside) {
        world = McWorld.Sample(LinearSampler, mc_uv);
        overlay = McOverlay.Sample(LinearSampler, mc_uv);
        mc_d = McDepth.Sample(PointSampler, mc_uv).r;
    }

    float host_d = HostDepth.Sample(PointSampler, input.uv).r;
    float mc_z = linear_depth(mc_d, McNear, McFar);
    float host_z = linear_depth(host_d, HostNear, HostFar);

    /*
     * Depth==1 is Minecraft sky/clear background. It must never cover SM64.
     * Real Steve/items/placed blocks are drawn only if they are in front of
     * the native SM64 surface at that pixel.
     */
    float world_visible =
        inside && mc_d < 0.999999 && mc_z <= host_z + DepthBias
        ? 1.0
        : 0.0;

    world *= world_visible;

    /*
     * Minecraft renders into a transparent target after the world capture,
     * so these buffers are already premultiplied. The HUD/GUI is screen-space
     * and always belongs on top of both Steve and SM64.
     */
    float3 rgb = overlay.rgb + world.rgb * (1.0 - overlay.a);
    float alpha = overlay.a + world.a * (1.0 - overlay.a);

    return float4(rgb, alpha);
}
)HLSL";

    ComPtr<ID3DBlob> vs_blob;
    ComPtr<ID3DBlob> ps_blob;

    if (!mc_overlay_compile_shader(
            shader_source,
            "VSMain",
            "vs_4_0",
            vs_blob
        )
        || !mc_overlay_compile_shader(
            shader_source,
            "PSMain",
            "ps_4_0",
            ps_blob
        )) {
        mc_overlay.shader_failed = true;
        return false;
    }

    if (FAILED(d3d.device->CreateVertexShader(
            vs_blob->GetBufferPointer(),
            vs_blob->GetBufferSize(),
            nullptr,
            mc_overlay.vertex_shader.GetAddressOf()
        ))
        || FAILED(d3d.device->CreatePixelShader(
            ps_blob->GetBufferPointer(),
            ps_blob->GetBufferSize(),
            nullptr,
            mc_overlay.pixel_shader.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    D3D11_INPUT_ELEMENT_DESC input_desc[2] = {
        {
            "POSITION",
            0,
            DXGI_FORMAT_R32G32_FLOAT,
            0,
            0,
            D3D11_INPUT_PER_VERTEX_DATA,
            0
        },
        {
            "TEXCOORD",
            0,
            DXGI_FORMAT_R32G32_FLOAT,
            0,
            8,
            D3D11_INPUT_PER_VERTEX_DATA,
            0
        }
    };

    if (FAILED(d3d.device->CreateInputLayout(
            input_desc,
            2,
            vs_blob->GetBufferPointer(),
            vs_blob->GetBufferSize(),
            mc_overlay.input_layout.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    static const McOverlayVertex vertices[4] = {
        {-1.0f,  1.0f, 0.0f, 0.0f},
        { 1.0f,  1.0f, 1.0f, 0.0f},
        {-1.0f, -1.0f, 0.0f, 1.0f},
        { 1.0f, -1.0f, 1.0f, 1.0f}
    };

    D3D11_BUFFER_DESC vb_desc = {};
    vb_desc.ByteWidth = sizeof(vertices);
    vb_desc.Usage = D3D11_USAGE_IMMUTABLE;
    vb_desc.BindFlags = D3D11_BIND_VERTEX_BUFFER;

    D3D11_SUBRESOURCE_DATA vb_data = {};
    vb_data.pSysMem = vertices;

    if (FAILED(d3d.device->CreateBuffer(
            &vb_desc,
            &vb_data,
            mc_overlay.vertex_buffer.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    D3D11_BUFFER_DESC cb_desc = {};
    cb_desc.ByteWidth = sizeof(McOverlayConstants);
    cb_desc.Usage = D3D11_USAGE_DYNAMIC;
    cb_desc.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    cb_desc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;

    if (FAILED(d3d.device->CreateBuffer(
            &cb_desc,
            nullptr,
            mc_overlay.constant_buffer.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    D3D11_SAMPLER_DESC linear_desc = {};
    linear_desc.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    linear_desc.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
    linear_desc.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
    linear_desc.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    linear_desc.MaxLOD = D3D11_FLOAT32_MAX;

    if (FAILED(d3d.device->CreateSamplerState(
            &linear_desc,
            mc_overlay.linear_sampler.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    D3D11_SAMPLER_DESC point_desc = linear_desc;
    point_desc.Filter = D3D11_FILTER_MIN_MAG_MIP_POINT;

    if (FAILED(d3d.device->CreateSamplerState(
            &point_desc,
            mc_overlay.point_sampler.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    D3D11_BLEND_DESC blend_desc = {};
    blend_desc.RenderTarget[0].BlendEnable = TRUE;
    blend_desc.RenderTarget[0].SrcBlend = D3D11_BLEND_ONE;
    blend_desc.RenderTarget[0].DestBlend = D3D11_BLEND_INV_SRC_ALPHA;
    blend_desc.RenderTarget[0].BlendOp = D3D11_BLEND_OP_ADD;
    blend_desc.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;
    blend_desc.RenderTarget[0].DestBlendAlpha = D3D11_BLEND_INV_SRC_ALPHA;
    blend_desc.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;
    blend_desc.RenderTarget[0].RenderTargetWriteMask =
        D3D11_COLOR_WRITE_ENABLE_ALL;

    if (FAILED(d3d.device->CreateBlendState(
            &blend_desc,
            mc_overlay.blend_state.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    D3D11_DEPTH_STENCIL_DESC depth_desc = {};
    depth_desc.DepthEnable = FALSE;
    depth_desc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    depth_desc.DepthFunc = D3D11_COMPARISON_ALWAYS;

    if (FAILED(d3d.device->CreateDepthStencilState(
            &depth_desc,
            mc_overlay.depth_state.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    D3D11_RASTERIZER_DESC raster_desc = {};
    raster_desc.FillMode = D3D11_FILL_SOLID;
    raster_desc.CullMode = D3D11_CULL_NONE;
    raster_desc.DepthClipEnable = TRUE;
    raster_desc.ScissorEnable = FALSE;

    if (FAILED(d3d.device->CreateRasterizerState(
            &raster_desc,
            mc_overlay.rasterizer_state.GetAddressOf()
        ))) {
        mc_overlay.shader_failed = true;
        return false;
    }

    mc_overlay.initialized = true;
    return true;
}

static bool mc_overlay_create_texture(
        uint32_t width,
        uint32_t height,
        DXGI_FORMAT format,
        ComPtr<ID3D11Texture2D> &texture,
        ComPtr<ID3D11ShaderResourceView> &srv
) {
    D3D11_TEXTURE2D_DESC desc = {};
    desc.Width = width;
    desc.Height = height;
    desc.MipLevels = 1;
    desc.ArraySize = 1;
    desc.Format = format;
    desc.SampleDesc.Count = 1;
    desc.Usage = D3D11_USAGE_DEFAULT;
    desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;

    if (FAILED(d3d.device->CreateTexture2D(
            &desc,
            nullptr,
            texture.GetAddressOf()
        ))) {
        return false;
    }

    D3D11_SHADER_RESOURCE_VIEW_DESC srv_desc = {};
    srv_desc.Format = format;
    srv_desc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
    srv_desc.Texture2D.MipLevels = 1;

    return SUCCEEDED(d3d.device->CreateShaderResourceView(
        texture.Get(),
        &srv_desc,
        srv.GetAddressOf()
    ));
}

static bool mc_overlay_ensure_textures(
        uint32_t width,
        uint32_t height
) {
    if (mc_overlay.width == width
            && mc_overlay.height == height
            && mc_overlay.world_texture.Get() != nullptr) {
        return true;
    }

    mc_overlay.world_texture.Reset();
    mc_overlay.mc_depth_texture.Reset();
    mc_overlay.overlay_texture.Reset();
    mc_overlay.world_srv.Reset();
    mc_overlay.mc_depth_srv.Reset();
    mc_overlay.overlay_srv.Reset();

    if (!mc_overlay_create_texture(
            width,
            height,
            DXGI_FORMAT_R8G8B8A8_UNORM,
            mc_overlay.world_texture,
            mc_overlay.world_srv
        )
        || !mc_overlay_create_texture(
            width,
            height,
            DXGI_FORMAT_R32_FLOAT,
            mc_overlay.mc_depth_texture,
            mc_overlay.mc_depth_srv
        )
        || !mc_overlay_create_texture(
            width,
            height,
            DXGI_FORMAT_R8G8B8A8_UNORM,
            mc_overlay.overlay_texture,
            mc_overlay.overlay_srv
        )) {
        mc_overlay.width = 0;
        mc_overlay.height = 0;
        return false;
    }

    mc_overlay.width = width;
    mc_overlay.height = height;
    return true;
}

static bool mc_overlay_upload_latest(
        float &mc_near,
        float &mc_far
) {
    if (!mc_overlay_open_mapping()) {
        return false;
    }

    uint64_t seq_before = mc_overlay_read<uint64_t>(16);
    if ((seq_before & 1ull) != 0ull
            || seq_before == 0
            || seq_before == mc_overlay.last_sequence) {
        return mc_overlay.last_sequence != 0;
    }

    MemoryBarrier();

    uint32_t width = mc_overlay_read<uint32_t>(8);
    uint32_t height = mc_overlay_read<uint32_t>(12);

    if (width == 0
            || height == 0
            || width > MC_OVERLAY_MAX_WIDTH
            || height > MC_OVERLAY_MAX_HEIGHT) {
        return false;
    }

    uint64_t pixels = (uint64_t) width * height;
    uint64_t bytes = pixels * 4ull;
    uint64_t end = MC_OVERLAY_HEADER + bytes * 3ull;

    if (end > MC_OVERLAY_FILE_BYTES) {
        return false;
    }

    if (!mc_overlay_ensure_textures(width, height)) {
        return false;
    }

    const uint8_t *world = mc_overlay.view + MC_OVERLAY_HEADER;
    const uint8_t *depth = world + bytes;
    const uint8_t *overlay = depth + bytes;

    d3d.context->UpdateSubresource(
        mc_overlay.world_texture.Get(),
        0,
        nullptr,
        world,
        width * 4,
        0
    );
    d3d.context->UpdateSubresource(
        mc_overlay.mc_depth_texture.Get(),
        0,
        nullptr,
        depth,
        width * 4,
        0
    );
    d3d.context->UpdateSubresource(
        mc_overlay.overlay_texture.Get(),
        0,
        nullptr,
        overlay,
        width * 4,
        0
    );

    MemoryBarrier();

    uint64_t seq_after = mc_overlay_read<uint64_t>(16);
    if (seq_after != seq_before || (seq_after & 1ull) != 0ull) {
        return mc_overlay.last_sequence != 0;
    }

    mc_near = mc_overlay_read<float>(36);
    mc_far = mc_overlay_read<float>(40);

    if (!(mc_near > 0.0f) || !(mc_far > mc_near)) {
        mc_near = 0.05f;
        mc_far = 256.0f;
    }

    mc_overlay.last_sequence = seq_after;
    return true;
}

static void mc_overlay_invalidate_sm64_cache(void) {
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

static void mc_overlay_render(void) {
    if (d3d.depth_shader_resource_view.Get() == nullptr) {
        return;
    }

    float mc_near = 0.05f;
    float mc_far = 256.0f;

    if (!mc_overlay_upload_latest(mc_near, mc_far)
            || !mc_overlay_init_pipeline()) {
        return;
    }

    D3D11_MAPPED_SUBRESOURCE mapped_cb = {};
    if (FAILED(d3d.context->Map(
            mc_overlay.constant_buffer.Get(),
            0,
            D3D11_MAP_WRITE_DISCARD,
            0,
            &mapped_cb
        ))) {
        return;
    }

    McOverlayConstants constants = {};
    constants.mc_near = mc_near;
    constants.mc_far = mc_far;

    /*
     * Most SM64 area graphs use 100..30000 N64 units. With the bridge's
     * 100-units-per-Minecraft-block scale that is 1..300 blocks.
     */
    constants.host_near = 1.0f;
    constants.host_far = 300.0f;
    constants.mc_aspect =
        (float) mc_overlay.width / (float) mc_overlay.height;
    constants.host_aspect =
        (float) d3d.current_width / (float) d3d.current_height;
    constants.depth_bias = 0.08f;

    memcpy(
        mapped_cb.pData,
        &constants,
        sizeof(constants)
    );
    d3d.context->Unmap(mc_overlay.constant_buffer.Get(), 0);

    /*
     * A depth surface cannot be both bound as DSV and SRV in D3D11. SM64 has
     * finished drawing at this point, so unbind the DSV and sample it.
     */
    d3d.context->OMSetRenderTargets(
        1,
        d3d.backbuffer_view.GetAddressOf(),
        nullptr
    );

    ID3D11ShaderResourceView *srvs[4] = {
        mc_overlay.world_srv.Get(),
        mc_overlay.mc_depth_srv.Get(),
        mc_overlay.overlay_srv.Get(),
        d3d.depth_shader_resource_view.Get()
    };
    d3d.context->PSSetShaderResources(0, 4, srvs);

    ID3D11SamplerState *samplers[2] = {
        mc_overlay.linear_sampler.Get(),
        mc_overlay.point_sampler.Get()
    };
    d3d.context->PSSetSamplers(0, 2, samplers);

    d3d.context->VSSetShader(
        mc_overlay.vertex_shader.Get(),
        nullptr,
        0
    );
    d3d.context->PSSetShader(
        mc_overlay.pixel_shader.Get(),
        nullptr,
        0
    );
    d3d.context->PSSetConstantBuffers(
        0,
        1,
        mc_overlay.constant_buffer.GetAddressOf()
    );

    d3d.context->IASetInputLayout(
        mc_overlay.input_layout.Get()
    );

    UINT stride = sizeof(McOverlayVertex);
    UINT offset = 0;
    d3d.context->IASetVertexBuffers(
        0,
        1,
        mc_overlay.vertex_buffer.GetAddressOf(),
        &stride,
        &offset
    );
    d3d.context->IASetPrimitiveTopology(
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP
    );

    d3d.context->OMSetBlendState(
        mc_overlay.blend_state.Get(),
        nullptr,
        0xffffffff
    );
    d3d.context->OMSetDepthStencilState(
        mc_overlay.depth_state.Get(),
        0
    );
    d3d.context->RSSetState(
        mc_overlay.rasterizer_state.Get()
    );

    D3D11_VIEWPORT viewport = {};
    viewport.Width = (float) d3d.current_width;
    viewport.Height = (float) d3d.current_height;
    viewport.MinDepth = 0.0f;
    viewport.MaxDepth = 1.0f;
    d3d.context->RSSetViewports(1, &viewport);

    d3d.context->Draw(4, 0);

    ID3D11ShaderResourceView *null_srvs[4] = {
        nullptr,
        nullptr,
        nullptr,
        nullptr
    };
    d3d.context->PSSetShaderResources(0, 4, null_srvs);

    mc_overlay_invalidate_sm64_cache();
}
