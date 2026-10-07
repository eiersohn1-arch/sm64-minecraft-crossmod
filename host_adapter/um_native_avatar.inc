// Native Minecraft avatar renderer for the SM64 D3D11 host.
//
// Universal Modder pattern 2 works best when guest geometry is drawn inside
// the host's own 3D pass instead of compositing a finished guest frame.  This
// first native slice replaces the third-person Minecraft avatar with a host-
// rendered block model.  The real Minecraft process still owns simulation,
// inventory, controls and pose; only the visual body is host-native.
//
// This intentionally uses simple colours for now.  Skin/item textures are
// exported from the user's Minecraft runtime in the next asset pass rather
// than committed to the repository.

struct UmNativeVertex {
    float position[4];
    float color[4];
};

struct UmNativeAvatarRenderer {
    Microsoft::WRL::ComPtr<ID3D11VertexShader> vs;
    Microsoft::WRL::ComPtr<ID3D11PixelShader> ps;
    Microsoft::WRL::ComPtr<ID3D11InputLayout> layout;
    Microsoft::WRL::ComPtr<ID3D11Buffer> vertices;
    Microsoft::WRL::ComPtr<ID3D11DepthStencilState> depth;
    Microsoft::WRL::ComPtr<ID3D11BlendState> blend;
    Microsoft::WRL::ComPtr<ID3D11RasterizerState> raster;
    bool ready = false;
};

static UmNativeAvatarRenderer um_native_avatar;

static bool um_native_create_pipeline() {
    if (um_native_avatar.ready) return true;

    static const char *shader = R"(
struct VSIn {
    float4 position : POSITION;
    float4 color : COLOR0;
};

struct VSOut {
    float4 position : SV_POSITION;
    float4 color : COLOR0;
};

VSOut VSMain(VSIn i) {
    VSOut o;
    o.position = i.position;
    o.color = i.color;
    return o;
}

float4 PSMain(VSOut i) : SV_TARGET {
    return i.color;
}
)";

    Microsoft::WRL::ComPtr<ID3DBlob> vsBlob;
    Microsoft::WRL::ComPtr<ID3DBlob> psBlob;
    Microsoft::WRL::ComPtr<ID3DBlob> errors;

    if (FAILED(d3d.D3DCompile(
        shader, std::strlen(shader), "UMNativeAvatar", nullptr, nullptr,
        "VSMain", "vs_4_0_level_9_1", D3DCOMPILE_OPTIMIZATION_LEVEL2, 0,
        vsBlob.GetAddressOf(), errors.GetAddressOf()
    ))) return false;

    errors.Reset();
    if (FAILED(d3d.D3DCompile(
        shader, std::strlen(shader), "UMNativeAvatar", nullptr, nullptr,
        "PSMain", "ps_4_0_level_9_1", D3DCOMPILE_OPTIMIZATION_LEVEL2, 0,
        psBlob.GetAddressOf(), errors.GetAddressOf()
    ))) return false;

    if (FAILED(d3d.device->CreateVertexShader(
        vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr,
        um_native_avatar.vs.GetAddressOf()
    ))) return false;

    if (FAILED(d3d.device->CreatePixelShader(
        psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr,
        um_native_avatar.ps.GetAddressOf()
    ))) return false;

    D3D11_INPUT_ELEMENT_DESC elements[] = {
        { "POSITION", 0, DXGI_FORMAT_R32G32B32A32_FLOAT, 0, 0,
          D3D11_INPUT_PER_VERTEX_DATA, 0 },
        { "COLOR", 0, DXGI_FORMAT_R32G32B32A32_FLOAT, 0, 16,
          D3D11_INPUT_PER_VERTEX_DATA, 0 },
    };
    if (FAILED(d3d.device->CreateInputLayout(
        elements, 2, vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(),
        um_native_avatar.layout.GetAddressOf()
    ))) return false;

    D3D11_BUFFER_DESC vb = {};
    vb.ByteWidth = sizeof(UmNativeVertex) * 512;
    vb.Usage = D3D11_USAGE_DYNAMIC;
    vb.BindFlags = D3D11_BIND_VERTEX_BUFFER;
    vb.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    if (FAILED(d3d.device->CreateBuffer(
        &vb, nullptr, um_native_avatar.vertices.GetAddressOf()
    ))) return false;

    D3D11_DEPTH_STENCIL_DESC depth = {};
    depth.DepthEnable = TRUE;
    depth.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ALL;
    depth.DepthFunc = D3D11_COMPARISON_LESS_EQUAL;
    if (FAILED(d3d.device->CreateDepthStencilState(
        &depth, um_native_avatar.depth.GetAddressOf()
    ))) return false;

    D3D11_BLEND_DESC blend = {};
    blend.RenderTarget[0].BlendEnable = FALSE;
    blend.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
    if (FAILED(d3d.device->CreateBlendState(
        &blend, um_native_avatar.blend.GetAddressOf()
    ))) return false;

    D3D11_RASTERIZER_DESC raster = {};
    raster.FillMode = D3D11_FILL_SOLID;
    raster.CullMode = D3D11_CULL_NONE;
    raster.DepthClipEnable = TRUE;
    if (FAILED(d3d.device->CreateRasterizerState(
        &raster, um_native_avatar.raster.GetAddressOf()
    ))) return false;

    um_native_avatar.ready = true;
    return true;
}

struct UmNativeVec3 {
    float x, y, z;
};

static UmNativeVec3 um_native_sub(UmNativeVec3 a, UmNativeVec3 b) {
    return { a.x - b.x, a.y - b.y, a.z - b.z };
}

static float um_native_dot(UmNativeVec3 a, UmNativeVec3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static UmNativeVec3 um_native_cross(UmNativeVec3 a, UmNativeVec3 b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    };
}

static UmNativeVec3 um_native_normalize(UmNativeVec3 v) {
    const float n = std::sqrt(um_native_dot(v, v));
    if (n <= 0.0001f) return { 0.0f, 0.0f, 1.0f };
    return { v.x / n, v.y / n, v.z / n };
}

struct UmNativeProjection {
    UmNativeVec3 eye;
    UmNativeVec3 right;
    UmNativeVec3 up;
    UmNativeVec3 forward;
    float tanHalfFov;
    float aspect;
};

static bool um_native_make_projection(
    const UmNativeCameraPose &camera,
    UmNativeProjection &out
) {
    if (!camera.valid || d3d.current_width <= 0 || d3d.current_height <= 0) {
        return false;
    }

    out.eye = { camera.eye[0], camera.eye[1], camera.eye[2] };
    UmNativeVec3 focus = {
        camera.focus[0], camera.focus[1], camera.focus[2]
    };
    out.forward = um_native_normalize(um_native_sub(focus, out.eye));

    UmNativeVec3 worldUp = { 0.0f, 1.0f, 0.0f };
    out.right = um_native_normalize(um_native_cross(out.forward, worldUp));
    out.up = um_native_normalize(um_native_cross(out.right, out.forward));

    float fov = camera.fov_degrees;
    if (!std::isfinite(fov) || fov < 20.0f || fov > 120.0f) fov = 70.0f;
    out.tanHalfFov = std::tan(fov * 0.5f * 0.01745329251994329577f);
    out.aspect = static_cast<float>(d3d.current_width)
        / static_cast<float>(d3d.current_height);
    return out.tanHalfFov > 0.0001f;
}

static bool um_native_project(
    const UmNativeProjection &p,
    UmNativeVec3 world,
    float colorR,
    float colorG,
    float colorB,
    UmNativeVertex &out
) {
    const UmNativeVec3 rel = um_native_sub(world, p.eye);
    const float x = um_native_dot(rel, p.right);
    const float y = um_native_dot(rel, p.up);
    const float z = um_native_dot(rel, p.forward);

    // SM64's perspective uses roughly 100..30000 world-unit near/far planes.
    constexpr float nearZ = 100.0f;
    constexpr float farZ = 30000.0f;
    if (!std::isfinite(z) || z <= nearZ + 1.0f) return false;

    const float ndcX = x / (z * p.tanHalfFov * p.aspect);
    const float ndcY = y / (z * p.tanHalfFov);
    const float depth = farZ / (farZ - nearZ)
        - (nearZ * farZ) / ((farZ - nearZ) * z);

    out.position[0] = ndcX;
    out.position[1] = ndcY;
    out.position[2] = std::clamp(depth, 0.0f, 1.0f);
    out.position[3] = 1.0f;
    out.color[0] = colorR;
    out.color[1] = colorG;
    out.color[2] = colorB;
    out.color[3] = 1.0f;
    return true;
}

static UmNativeVec3 um_native_rotate_y(
    UmNativeVec3 local,
    const UmNativeAvatarPose &avatar
) {
    const float yaw = avatar.yaw_degrees * 0.01745329251994329577f;
    const float c = std::cos(yaw);
    const float s = std::sin(yaw);
    return {
        avatar.x + local.x * c - local.z * s,
        avatar.y + local.y,
        avatar.z + local.x * s + local.z * c
    };
}

static bool um_native_append_box(
    UmNativeVertex *vertices,
    int &count,
    int capacity,
    const UmNativeProjection &projection,
    const UmNativeAvatarPose &avatar,
    float minX, float minY, float minZ,
    float maxX, float maxY, float maxZ,
    float r, float g, float b
) {
    if (count + 36 > capacity) return false;

    UmNativeVec3 p[8] = {
        { minX, minY, minZ }, { maxX, minY, minZ },
        { maxX, maxY, minZ }, { minX, maxY, minZ },
        { minX, minY, maxZ }, { maxX, minY, maxZ },
        { maxX, maxY, maxZ }, { minX, maxY, maxZ },
    };

    for (auto &v : p) v = um_native_rotate_y(v, avatar);

    static const int faces[6][6] = {
        {0,1,2, 0,2,3}, // -Z
        {5,4,7, 5,7,6}, // +Z
        {4,0,3, 4,3,7}, // -X
        {1,5,6, 1,6,2}, // +X
        {3,2,6, 3,6,7}, // top
        {4,5,1, 4,1,0}, // bottom
    };
    static const float shade[6] = {
        0.82f, 0.92f, 0.74f, 0.78f, 1.0f, 0.62f
    };

    for (int face = 0; face < 6; ++face) {
        for (int i = 0; i < 6; ++i) {
            UmNativeVertex v{};
            if (!um_native_project(
                projection,
                p[faces[face][i]],
                r * shade[face],
                g * shade[face],
                b * shade[face],
                v
            )) return false;
            vertices[count++] = v;
        }
    }
    return true;
}

static void um_draw_native_avatar() {
    UmNativeAvatarPose avatar{};
    UmNativeCameraPose camera{};
    if (!um_passthrough_get_native_avatar(&avatar)
        || !um_passthrough_get_native_camera(&camera)
        || !avatar.valid
        || avatar.first_person) {
        return;
    }
    if (!um_native_create_pipeline()) return;

    UmNativeProjection projection{};
    if (!um_native_make_projection(camera, projection)) return;

    UmNativeVertex verts[512] = {};
    int count = 0;

    // 1 Minecraft block = 100 SM64 units.  Classic player proportions:
    // 8px head, 12px torso, 12px legs, 4px wide limbs = ~1.8 blocks tall.
    constexpr float px = 5.625f;
    const float legH = 12.0f * px;
    const float torsoH = 12.0f * px;
    const float headH = 8.0f * px;
    const float torsoHalf = 4.0f * px;
    const float limbHalf = 2.0f * px;
    const float depthHalf = 2.0f * px;

    const float legTop = legH;
    const float torsoTop = legH + torsoH;
    const float headTop = torsoTop + headH;

    // Legs.
    um_native_append_box(
        verts, count, 512, projection, avatar,
        -4.0f * px, 0.0f, -depthHalf,
        0.0f, legTop, depthHalf,
        0.25f, 0.18f, 0.62f
    );
    um_native_append_box(
        verts, count, 512, projection, avatar,
        0.0f, 0.0f, -depthHalf,
        4.0f * px, legTop, depthHalf,
        0.25f, 0.18f, 0.62f
    );

    // Torso.
    um_native_append_box(
        verts, count, 512, projection, avatar,
        -torsoHalf, legTop, -depthHalf,
        torsoHalf, torsoTop, depthHalf,
        0.00f, 0.63f, 0.67f
    );

    // Arms: cyan sleeve over skin forearm.
    const float armOuter = 6.0f * px;
    const float sleeveBottom = torsoTop - 4.0f * px;
    um_native_append_box(
        verts, count, 512, projection, avatar,
        -armOuter, sleeveBottom, -depthHalf,
        -torsoHalf, torsoTop, depthHalf,
        0.00f, 0.63f, 0.67f
    );
    um_native_append_box(
        verts, count, 512, projection, avatar,
        torsoHalf, sleeveBottom, -depthHalf,
        armOuter, torsoTop, depthHalf,
        0.00f, 0.63f, 0.67f
    );
    um_native_append_box(
        verts, count, 512, projection, avatar,
        -armOuter, legTop, -depthHalf,
        -torsoHalf, sleeveBottom, depthHalf,
        0.68f, 0.43f, 0.30f
    );
    um_native_append_box(
        verts, count, 512, projection, avatar,
        torsoHalf, legTop, -depthHalf,
        armOuter, sleeveBottom, depthHalf,
        0.68f, 0.43f, 0.30f
    );

    // Head.  From the normal rear camera this is the classic dark hair side;
    // a skin texture exported from the user's Minecraft install will replace
    // these flat face colours in the next asset pass.
    um_native_append_box(
        verts, count, 512, projection, avatar,
        -4.0f * px, torsoTop, -4.0f * px,
        4.0f * px, headTop, 4.0f * px,
        0.22f, 0.12f, 0.055f
    );

    if (count <= 0) return;

    D3D11_MAPPED_SUBRESOURCE mapped = {};
    if (FAILED(d3d.context->Map(
        um_native_avatar.vertices.Get(), 0,
        D3D11_MAP_WRITE_DISCARD, 0, &mapped
    ))) return;
    std::memcpy(mapped.pData, verts, sizeof(UmNativeVertex) * count);
    d3d.context->Unmap(um_native_avatar.vertices.Get(), 0);

    D3D11_VIEWPORT vp = {};
    vp.Width = static_cast<float>(d3d.current_width);
    vp.Height = static_cast<float>(d3d.current_height);
    vp.MinDepth = 0.0f;
    vp.MaxDepth = 1.0f;
    d3d.context->RSSetViewports(1, &vp);

    const UINT stride = sizeof(UmNativeVertex);
    const UINT offset = 0;
    ID3D11Buffer *vb = um_native_avatar.vertices.Get();
    d3d.context->IASetInputLayout(um_native_avatar.layout.Get());
    d3d.context->IASetVertexBuffers(0, 1, &vb, &stride, &offset);
    d3d.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    d3d.context->VSSetShader(um_native_avatar.vs.Get(), nullptr, 0);
    d3d.context->PSSetShader(um_native_avatar.ps.Get(), nullptr, 0);
    d3d.context->RSSetState(um_native_avatar.raster.Get());
    d3d.context->OMSetRenderTargets(
        1, d3d.backbuffer_view.GetAddressOf(), d3d.depth_stencil_view.Get()
    );
    d3d.context->OMSetDepthStencilState(um_native_avatar.depth.Get(), 0);
    d3d.context->OMSetBlendState(
        um_native_avatar.blend.Get(), nullptr, 0xFFFFFFFF
    );
    d3d.context->Draw(static_cast<UINT>(count), 0);

    // The MCPT overlay path immediately rebinds its own pipeline.  Still
    // invalidate the SM64 cache so the next game frame never assumes these
    // raw D3D11 bindings are its own.
    um_invalidate_sm64_state();
}
