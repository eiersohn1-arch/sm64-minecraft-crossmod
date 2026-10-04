#include "../crossmod_bridge.h"

 /*
 * Minecraft -> SM64 D3D11 compositor.
 *
 * This file is copied into sm64-port/src/pc/gfx and included directly by
 * gfx_direct3d11.cpp after the private d3d state is declared. Keeping it as an
 * .inc lets the crossmod use the port's existing D3D11 device/backbuffer
 * without changing any public SM64 renderer interfaces.
 */

#define MC_OVERLAY_MAGIC 0x5450434Du /* "MCPT" */
#define MC_OVERLAY_VERSION 1u
#define MC_OVERLAY_HEADER 4096u
#define MC_OVERLAY_SLOT_DESC 256u
#define MC_OVERLAY_SLOT_DESC_BYTES 128u
#define MC_OVERLAY_MAX_WIDTH 3840u
#define MC_OVERLAY_MAX_HEIGHT 2160u
#define MC_OVERLAY_MAX_PIXELS ((uint64_t) MC_OVERLAY_MAX_WIDTH * MC_OVERLAY_MAX_HEIGHT)
#define MC_OVERLAY_MAX_LAYER_BYTES (MC_OVERLAY_MAX_PIXELS * 4ull)

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
    float mc_flags;

    float warp_row0[4];
    float warp_row1[4];
    float warp_row2[4];
    float warp_t[4];
    float warp_tan[4];
};

struct McOverlayPose {
    uint64_t host_frame = 0;
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    float yaw = 0.0f;
    float pitch = 0.0f;
    float roll = 0.0f;
    float fov = 45.0f;
    bool valid = false;
};

static struct {
    HANDLE mapping = nullptr;
    const uint8_t *view = nullptr;
    SIZE_T view_bytes = 0;
    DWORD next_open_attempt = 0;

    int32_t slots = 0;
    int64_t stride = 0;
    int64_t last_publish = -1;
    int32_t mc_flags = 0;
    uint32_t width = 0;
    uint32_t height = 0;
    McOverlayPose mc_pose;

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

    bool window_overlay_mode = false;
    bool window_hidden = false;
    bool host_focus_claimed = false;
    int last_window_x = 0x7fffffff;
    int last_window_y = 0x7fffffff;
    int last_window_width = 0;
    int last_window_height = 0;
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
    mc_overlay.view_bytes = 0;
    mc_overlay.slots = 0;
    mc_overlay.stride = 0;
    mc_overlay.last_publish = -1;
    mc_overlay.host_focus_claimed = false;
}

static bool mc_overlay_open_mapping(void) {
    if (mc_overlay.view != nullptr) {
        return true;
    }

    DWORD now = GetTickCount();
    if (now < mc_overlay.next_open_attempt) {
        return false;
    }
    mc_overlay.next_open_attempt = now + 1000;

    /*
     * This is the exact transport shape used by universal-modder's
     * Minecraft x GTA passthrough: Minecraft creates a pagefile-backed named
     * mapping and the host opens it by name.
     */
    mc_overlay.mapping = OpenFileMappingW(
        FILE_MAP_READ,
        FALSE,
        L"Local\\MCPassthroughFrame"
    );
    if (mc_overlay.mapping == nullptr) {
        return false;
    }

    const uint8_t *header = static_cast<const uint8_t *>(
        MapViewOfFile(
            mc_overlay.mapping,
            FILE_MAP_READ,
            0,
            0,
            MC_OVERLAY_HEADER
        )
    );
    if (header == nullptr) {
        mc_overlay_close_mapping();
        return false;
    }

    uint32_t magic;
    uint32_t version;
    int32_t slots;
    int64_t stride;
    memcpy(&magic, header + 0, sizeof(magic));
    memcpy(&version, header + 4, sizeof(version));
    memcpy(&slots, header + 12, sizeof(slots));
    memcpy(&stride, header + 16, sizeof(stride));

    UnmapViewOfFile(header);

    if (magic != MC_OVERLAY_MAGIC
            || version != MC_OVERLAY_VERSION
            || slots <= 0
            || slots > 8
            || stride <= 0
            || (uint64_t) stride > MC_OVERLAY_MAX_LAYER_BYTES * 3ull) {
        mc_overlay_close_mapping();
        return false;
    }

    uint64_t bytes =
        (uint64_t) MC_OVERLAY_HEADER
        + (uint64_t) stride * (uint64_t) slots;

    mc_overlay.view = static_cast<const uint8_t *>(
        MapViewOfFile(
            mc_overlay.mapping,
            FILE_MAP_READ,
            0,
            0,
            (SIZE_T) bytes
        )
    );

    if (mc_overlay.view == nullptr) {
        mc_overlay_close_mapping();
        return false;
    }

    mc_overlay.view_bytes = (SIZE_T) bytes;
    mc_overlay.slots = slots;
    mc_overlay.stride = stride;
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
    float McFlags;

    float4 WarpRow0;
    float4 WarpRow1;
    float4 WarpRow2;
    float4 WarpT;
    // x = tan(host vertical fov / 2)
    // y = tan(Minecraft vertical fov / 2)
    // z = Minecraft aspect
    // w = reprojection enabled
    float4 WarpTan;
};

float mc_linear_depth(float d) {
    bool reversed = fmod(floor(McFlags / 4.0), 2.0) > 0.5;

    if (reversed) {
        if (d <= 0.000001) {
            return 1.0e20;
        }
        return (McNear * McFar)
            / max(McNear + d * (McFar - McNear), 1.0e-6);
    }

    if (d >= 0.999999) {
        return 1.0e20;
    }
    return (McNear * McFar)
        / max(McFar - d * (McFar - McNear), 1.0e-6);
}

float host_linear_depth(float d) {
    if (d >= 0.999999) {
        return 1.0e20;
    }
    return (HostNear * HostFar)
        / max(HostFar - d * (HostFar - HostNear), 1.0e-6);
}

float2 mc_uv_from_ndc(float2 ndc) {
    bool bottom_up = fmod(floor(McFlags / 2.0), 2.0) > 0.5;
    float2 uv = ndc * 0.5 + 0.5;
    if (!bottom_up) {
        uv.y = 1.0 - uv.y;
    }
    return uv;
}

float4 PSMain(VSOutput input) : SV_TARGET {
    float host_d = HostDepth.Sample(PointSampler, input.uv).r;
    float host_z = host_linear_depth(host_d);

    // Screen-space sampling for hand/HUD is never reprojected.
    float2 screen_ndc = float2(
        input.uv.x * 2.0 - 1.0,
        1.0 - input.uv.y * 2.0
    );
    float2 overlay_uv = mc_uv_from_ndc(screen_ndc);
    float4 overlay = McOverlay.Sample(LinearSampler, overlay_uv);

    /*
     * Defensive fallback for older/driver-specific Minecraft render paths:
     * an RGBA clear can occasionally arrive as opaque black if alpha writes
     * were masked. Never let that clear colour cover the native SM64 frame.
     * Actual GUI pixels (including dark inventory panels) contain non-zero
     * colour/edge data and remain composited normally.
     */
    if (overlay.a > 0.999
            && max(max(abs(overlay.r), abs(overlay.g)), abs(overlay.b))
                < (0.5 / 255.0)) {
        overlay = float4(0.0, 0.0, 0.0, 0.0);
    }

    // Direct fallback for the first frame or if a pose is not available.
    float mc_ndc_x =
        screen_ndc.x * HostAspect / max(McAspect, 1.0e-6);
    float2 world_uv = mc_uv_from_ndc(
        float2(mc_ndc_x, screen_ndc.y)
    );
    bool inside =
        all(world_uv >= 0.0) && all(world_uv <= 1.0);

    float mc_z = 1.0e20;

    if (WarpTan.w > 0.5 && host_z < 1.0e19) {
        /*
         * Port of Universal Modder's Minecraft x GTA pose reprojection:
         * march the current host-camera ray through the Minecraft frame
         * rendered from the older captured pose, then refine the crossing.
         */
        float3 ray = float3(
            screen_ndc.x * WarpTan.x * HostAspect,
            screen_ndc.y * WarpTan.x,
            -1.0
        );
        float2 mc_scale = float2(
            WarpTan.y * WarpTan.z,
            WarpTan.y
        );

        float z_near = max(HostNear, 0.2);
        float z_far = max(
            min(host_z + DepthBias, min(HostFar, 400.0)),
            z_near * 2.0
        );

        float2 settled_ndc = 0.0;
        inside = false;

        [loop] for (int i = 0; i < 24; ++i) {
            float t = i / 23.0;
            float z = z_near * pow(z_far / z_near, t);
            float3 p = ray * z;

            float3 pm = float3(
                dot(WarpRow0.xyz, p),
                dot(WarpRow1.xyz, p),
                dot(WarpRow2.xyz, p)
            ) + WarpT.xyz;

            if (pm.z > -1.0e-3) {
                continue;
            }

            float2 n = pm.xy / -pm.z / mc_scale;
            if (any(abs(n) > 1.0)) {
                continue;
            }

            float2 sample_uv = mc_uv_from_ndc(n);
            float z_surface = mc_linear_depth(
                McDepth.SampleLevel(
                    PointSampler,
                    sample_uv,
                    0
                ).r
            );

            if (z_surface > -pm.z + 0.03) {
                continue;
            }

            float z_host = z;
            settled_ndc = n;

            [loop] for (int k = 0; k < 3; ++k) {
                float3 pk = ray * z_host;
                float3 mk = float3(
                    dot(WarpRow0.xyz, pk),
                    dot(WarpRow1.xyz, pk),
                    dot(WarpRow2.xyz, pk)
                ) + WarpT.xyz;

                if (mk.z > -1.0e-3) {
                    break;
                }

                float2 nk = mk.xy / -mk.z / mc_scale;
                if (any(abs(nk) > 1.0)) {
                    break;
                }

                float zk = mc_linear_depth(
                    McDepth.SampleLevel(
                        PointSampler,
                        mc_uv_from_ndc(nk),
                        0
                    ).r
                );

                if (zk > 1.0e19) {
                    break;
                }

                settled_ndc = nk;

                float3 q =
                    float3(nk * mc_scale, -1.0) * zk
                    - WarpT.xyz;

                z_host = -(
                    q.x * WarpRow0.z
                    + q.y * WarpRow1.z
                    + q.z * WarpRow2.z
                );
            }

            world_uv = mc_uv_from_ndc(settled_ndc);
            mc_z = z_host;
            inside = true;
            break;
        }
    } else if (inside) {
        mc_z = mc_linear_depth(
            McDepth.SampleLevel(
                PointSampler,
                world_uv,
                0
            ).r
        );
    }

    float4 world = inside
        ? McWorld.Sample(LinearSampler, world_uv)
        : float4(0.0, 0.0, 0.0, 0.0);

    float visible =
        inside
        && mc_z < 1.0e19
        && mc_z <= host_z + DepthBias
        ? 1.0
        : 0.0;

    world *= visible;

    /*
     * Minecraft world/overlay buffers are premultiplied-alpha layers.
     * The HUD stays screen-space while the 3D world is reprojected.
     */
    float3 rgb =
        overlay.rgb + world.rgb * (1.0 - overlay.a);
    float alpha =
        overlay.a + world.a * (1.0 - overlay.a);

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
        float &mc_far,
        int32_t &mc_flags
) {
    if (!mc_overlay_open_mapping()) {
        return false;
    }

    int64_t published = mc_overlay_read<int64_t>(32);
    if (published == mc_overlay.last_publish) {
        return mc_overlay.last_publish >= 0;
    }

    int32_t slot = mc_overlay_read<int32_t>(40);
    if (slot < 0 || slot >= mc_overlay.slots) {
        return false;
    }

    size_t desc_offset =
        MC_OVERLAY_SLOT_DESC
        + (size_t) MC_OVERLAY_SLOT_DESC_BYTES * (size_t) slot;

    uint64_t seq_before = mc_overlay_read<uint64_t>(desc_offset);
    if ((seq_before & 1ull) != 0ull) {
        return false;
    }

    MemoryBarrier();

    uint32_t width =
        mc_overlay_read<uint32_t>(desc_offset + 24);
    uint32_t height =
        mc_overlay_read<uint32_t>(desc_offset + 28);

    if (width == 0
            || height == 0
            || width > MC_OVERLAY_MAX_WIDTH
            || height > MC_OVERLAY_MAX_HEIGHT) {
        return false;
    }

    uint64_t layer_bytes =
        (uint64_t) width * (uint64_t) height * 4ull;
    uint64_t base =
        (uint64_t) MC_OVERLAY_HEADER
        + (uint64_t) mc_overlay.stride * (uint64_t) slot;
    uint64_t end = base + layer_bytes * 3ull;

    if (end > (uint64_t) mc_overlay.view_bytes) {
        return false;
    }

    if (!mc_overlay_ensure_textures(width, height)) {
        return false;
    }

    const uint8_t *world = mc_overlay.view + base;
    const uint8_t *depth = world + layer_bytes;
    const uint8_t *overlay = depth + layer_bytes;

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

    uint64_t seq_after = mc_overlay_read<uint64_t>(desc_offset);
    if (seq_after != seq_before || (seq_after & 1ull) != 0ull) {
        return false;
    }

    mc_near = mc_overlay_read<float>(desc_offset + 32);
    mc_far = mc_overlay_read<float>(desc_offset + 36);
    mc_flags = mc_overlay_read<int32_t>(desc_offset + 44);

    mc_overlay.mc_pose.host_frame =
        mc_overlay_read<uint64_t>(desc_offset + 16);
    mc_overlay.mc_pose.fov =
        mc_overlay_read<float>(desc_offset + 40);
    mc_overlay.mc_pose.x =
        mc_overlay_read<double>(desc_offset + 48);
    mc_overlay.mc_pose.y =
        mc_overlay_read<double>(desc_offset + 56);
    mc_overlay.mc_pose.z =
        mc_overlay_read<double>(desc_offset + 64);
    mc_overlay.mc_pose.yaw =
        mc_overlay_read<float>(desc_offset + 72);
    mc_overlay.mc_pose.pitch =
        mc_overlay_read<float>(desc_offset + 76);
    mc_overlay.mc_pose.roll =
        mc_overlay_read<float>(desc_offset + 80);
    mc_overlay.mc_pose.valid =
        mc_overlay.mc_pose.fov > 1.0f
        && mc_overlay.mc_pose.fov < 170.0f;

    if (!(mc_near > 0.0f) || !(mc_far > mc_near)) {
        mc_near = 0.05f;
        mc_far = 256.0f;
    }

    mc_overlay.mc_flags = mc_flags;
    mc_overlay.last_publish = published;
    return true;
}


static void mc_overlay_camera_rotation(
        float yaw,
        float pitch,
        float roll,
        float out[3][3]
) {
    const float d2r = 3.14159265358979323846f / 180.0f;
    const float a = 3.14159265358979323846f - yaw * d2r;
    const float b = -pitch * d2r;
    const float c = roll * d2r;

    const float ca = cosf(a);
    const float sa = sinf(a);
    const float cb = cosf(b);
    const float sb = sinf(b);
    const float cc = cosf(c);
    const float sc = sinf(c);

    const float ry[3][3] = {
        {ca, 0.0f, sa},
        {0.0f, 1.0f, 0.0f},
        {-sa, 0.0f, ca}
    };
    const float rx[3][3] = {
        {1.0f, 0.0f, 0.0f},
        {0.0f, cb, -sb},
        {0.0f, sb, cb}
    };
    const float rz[3][3] = {
        {cc, -sc, 0.0f},
        {sc, cc, 0.0f},
        {0.0f, 0.0f, 1.0f}
    };

    float temp[3][3] = {};

    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            for (int k = 0; k < 3; ++k) {
                temp[i][j] += ry[i][k] * rx[k][j];
            }
        }
    }

    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            out[i][j] = 0.0f;
            for (int k = 0; k < 3; ++k) {
                out[i][j] += temp[i][k] * rz[k][j];
            }
        }
    }
}

static void mc_overlay_build_reprojection(
        McOverlayConstants &constants
) {
    constants.warp_row0[0] = 1.0f;
    constants.warp_row0[1] = 0.0f;
    constants.warp_row0[2] = 0.0f;

    constants.warp_row1[0] = 0.0f;
    constants.warp_row1[1] = 1.0f;
    constants.warp_row1[2] = 0.0f;

    constants.warp_row2[0] = 0.0f;
    constants.warp_row2[1] = 0.0f;
    constants.warp_row2[2] = 1.0f;

    constants.warp_t[0] = 0.0f;
    constants.warp_t[1] = 0.0f;
    constants.warp_t[2] = 0.0f;

    constants.warp_tan[0] = 1.0f;
    constants.warp_tan[1] = 1.0f;
    constants.warp_tan[2] = constants.mc_aspect;
    constants.warp_tan[3] = 0.0f;

    if (!mc_overlay.mc_pose.valid) {
        return;
    }

    CrossmodRenderPose host_pose;
    if (!crossmod_bridge_get_render_pose(&host_pose)
            || host_pose.fov <= 1.0f
            || host_pose.fov >= 170.0f) {
        return;
    }

    float host_rotation[3][3];
    float mc_rotation[3][3];

    mc_overlay_camera_rotation(
        host_pose.yaw,
        host_pose.pitch,
        host_pose.roll,
        host_rotation
    );
    mc_overlay_camera_rotation(
        mc_overlay.mc_pose.yaw,
        mc_overlay.mc_pose.pitch,
        mc_overlay.mc_pose.roll,
        mc_rotation
    );

    float warp[3][3] = {};
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            for (int k = 0; k < 3; ++k) {
                warp[i][j] +=
                    mc_rotation[k][i]
                    * host_rotation[k][j];
            }
        }
    }

    for (int j = 0; j < 3; ++j) {
        constants.warp_row0[j] = warp[0][j];
        constants.warp_row1[j] = warp[1][j];
        constants.warp_row2[j] = warp[2][j];
    }

    const float delta[3] = {
        host_pose.camera_x - (float) mc_overlay.mc_pose.x,
        host_pose.camera_y - (float) mc_overlay.mc_pose.y,
        host_pose.camera_z - (float) mc_overlay.mc_pose.z
    };

    for (int i = 0; i < 3; ++i) {
        constants.warp_t[i] =
            mc_rotation[0][i] * delta[0]
            + mc_rotation[1][i] * delta[1]
            + mc_rotation[2][i] * delta[2];
    }

    const float d2r = 3.14159265358979323846f / 180.0f;
    constants.warp_tan[0] =
        tanf(host_pose.fov * d2r * 0.5f);
    constants.warp_tan[1] =
        tanf(mc_overlay.mc_pose.fov * d2r * 0.5f);
    constants.warp_tan[2] = constants.mc_aspect;
    constants.warp_tan[3] = 1.0f;
}


static void mc_overlay_claim_host_focus(void) {
    if (mc_overlay.host_focus_claimed) {
        return;
    }

    HWND host = gfx_dxgi_get_h_wnd();
    if (host == nullptr) {
        return;
    }

    /*
     * Minecraft backgrounds itself as soon as a playable guest world exists.
     * Claim focus exactly once when the first guest frame reaches SM64.
     * Do not steal focus again after the user intentionally Alt-Tabs.
     */
    ShowWindow(host, SW_RESTORE);
    BringWindowToTop(host);
    SetForegroundWindow(host);
    SetActiveWindow(host);

    mc_overlay.host_focus_claimed = true;
}

static void mc_overlay_sync_window(void) {
    if (mc_overlay.view == nullptr) {
        return;
    }

    HWND host = gfx_dxgi_get_h_wnd();
    HWND minecraft = reinterpret_cast<HWND>(
        static_cast<uintptr_t>(mc_overlay_read<uint64_t>(64))
    );

    if (minecraft == nullptr || !IsWindow(minecraft)) {
        if (mc_overlay.window_overlay_mode) {
            /*
             * The Minecraft process/window went away. The host belongs to this
             * crossmod session, so close it instead of leaving an invisible
             * top-most overlay process behind.
             */
            PostMessageW(host, WM_CLOSE, 0, 0);
        }
        return;
    }

    int x = mc_overlay_read<int32_t>(48);
    int y = mc_overlay_read<int32_t>(52);
    int width = mc_overlay_read<int32_t>(56);
    int height = mc_overlay_read<int32_t>(60);

    if (width < 64 || height < 64 || width > 10000 || height > 10000) {
        return;
    }

    /*
     * Minecraft stays the focused/input window. SM64 is an opaque,
     * click-through, no-activate overlay exactly over Minecraft's content
     * area. Therefore keyboard, mouse, hotbar and inventory input continue to
     * be handled by Minecraft while the player sees the composited SM64 frame.
     */
    if (!mc_overlay.window_overlay_mode) {
        SetWindowLongPtrW(host, GWL_STYLE, WS_POPUP | WS_VISIBLE);

        LONG_PTR ex_style = GetWindowLongPtrW(host, GWL_EXSTYLE);
        ex_style |= WS_EX_LAYERED
                 | WS_EX_TRANSPARENT
                 | WS_EX_NOACTIVATE
                 | WS_EX_TOOLWINDOW;
        SetWindowLongPtrW(host, GWL_EXSTYLE, ex_style);

        SetLayeredWindowAttributes(
            host,
            0,
            255,
            LWA_ALPHA
        );

        mc_overlay.window_overlay_mode = true;
    }

    bool minecraft_focused = GetForegroundWindow() == minecraft;

    if (!minecraft_focused) {
        if (!mc_overlay.window_hidden) {
            ShowWindow(host, SW_HIDE);
            mc_overlay.window_hidden = true;
        }
        return;
    }

    if (mc_overlay.window_hidden) {
        ShowWindow(host, SW_SHOWNOACTIVATE);
        mc_overlay.window_hidden = false;
    }

    if (x != mc_overlay.last_window_x
            || y != mc_overlay.last_window_y
            || width != mc_overlay.last_window_width
            || height != mc_overlay.last_window_height) {
        SetWindowPos(
            host,
            HWND_TOPMOST,
            x,
            y,
            width,
            height,
            SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW
        );

        mc_overlay.last_window_x = x;
        mc_overlay.last_window_y = y;
        mc_overlay.last_window_width = width;
        mc_overlay.last_window_height = height;
    } else {
        SetWindowPos(
            host,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        );
    }
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
    int32_t mc_flags = 0;

    if (!mc_overlay_upload_latest(mc_near, mc_far, mc_flags)
            || !mc_overlay_init_pipeline()) {
        return;
    }

    mc_overlay_claim_host_focus();

    /*
     * Single-host-window mode: SM64 stays the normal visible/focused window.
     * Minecraft is moved off-screen by the guest mod and only contributes
     * colour/depth/HUD through shared memory.
     */
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
    constants.mc_flags = (float) mc_flags;

    mc_overlay_build_reprojection(constants);

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

    /*
     * SM64 binds its per-frame constant buffer only during renderer init.
     * The compositor temporarily uses slot b0, so restore SM64's buffer before
     * the next frame instead of relying on the state cache.
     */
    d3d.context->PSSetConstantBuffers(
        0,
        1,
        d3d.per_frame_cb.GetAddressOf()
    );

    mc_overlay_invalidate_sm64_cache();
}
