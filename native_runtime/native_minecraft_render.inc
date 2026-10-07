// Injected inside gfx_direct3d11.cpp's private namespace.
// World geometry uses the existing SM64 depth buffer. HUD is a separate pass.

struct NmVertex {
    float x, y, z;
    float r, g, b, a;
};

struct NmPoint {
    float x, y, z;
};

struct NmFace {
    NmVertex v[6];
};

static ComPtr<ID3D11VertexShader> nm_vs;
static ComPtr<ID3D11PixelShader> nm_ps;
static ComPtr<ID3D11InputLayout> nm_layout;
static ComPtr<ID3D11Buffer> nm_vb;
static ComPtr<ID3D11BlendState> nm_alpha_blend;
static ComPtr<ID3D11DepthStencilState> nm_world_depth;
static ComPtr<ID3D11DepthStencilState> nm_hud_depth;
static ComPtr<ID3D11RasterizerState> nm_no_cull;
static bool nm_pipeline_ready = false;

static std::vector<NmVertex> nm_world_vertices;
static std::vector<NmVertex> nm_hud_vertices;

static float nm_px = 0.0f;
static float nm_py = 0.0f;
static float nm_pz = 0.0f;
static float nm_yaw = 0.0f;
static float nm_pitch = 0.0f;
static int nm_first_person = 0;
static int nm_slot = 0;
static int nm_inventory = 0;

static void nm_push_tri(
    std::vector<NmVertex> &out,
    const NmVertex &a, const NmVertex &b, const NmVertex &c
) {
    out.push_back(a);
    out.push_back(b);
    out.push_back(c);
}

static void nm_push_quad(
    std::vector<NmVertex> &out,
    const NmVertex &a, const NmVertex &b,
    const NmVertex &c, const NmVertex &d
) {
    nm_push_tri(out, a, b, c);
    nm_push_tri(out, a, c, d);
}

static void nm_push_rect_ndc(
    float x0, float y0, float x1, float y1,
    float r, float g, float b, float a
) {
    NmVertex v0{x0,y0,0.0f,r,g,b,a};
    NmVertex v1{x1,y0,0.0f,r,g,b,a};
    NmVertex v2{x1,y1,0.0f,r,g,b,a};
    NmVertex v3{x0,y1,0.0f,r,g,b,a};
    nm_push_quad(nm_hud_vertices, v0,v1,v2,v3);
}

static void nm_push_rect_px(
    float x, float y, float w, float h,
    float r, float g, float b, float a
) {
    const float sw = (float)d3d.current_width;
    const float sh = (float)d3d.current_height;
    const float x0 = x / sw * 2.0f - 1.0f;
    const float x1 = (x+w) / sw * 2.0f - 1.0f;
    const float y0 = 1.0f - y / sh * 2.0f;
    const float y1 = 1.0f - (y+h) / sh * 2.0f;
    nm_push_rect_ndc(x0,y0,x1,y1,r,g,b,a);
}

static NmPoint nm_camera_forward() {
    const float deg = 0.01745329251994329577f;
    const float yaw = nm_yaw * deg;
    const float pitch = nm_pitch * deg;
    const float cp = std::cos(pitch);
    return NmPoint{
        -std::sin(yaw) * cp,
        -std::sin(pitch),
        -std::cos(yaw) * cp
    };
}

static bool nm_project(
    const NmPoint &p, NmVertex &out,
    float r, float g, float b, float a
) {
    constexpr float NEAR_Z = 100.0f;
    constexpr float FAR_Z = 30000.0f;
    constexpr float FOV = 70.0f;
    const float deg = 0.01745329251994329577f;

    const NmPoint forward = nm_camera_forward();
    const float yaw = nm_yaw * deg;
    const NmPoint right{std::cos(yaw), 0.0f, -std::sin(yaw)};
    const NmPoint up{
        right.y * forward.z - right.z * forward.y,
        right.z * forward.x - right.x * forward.z,
        right.x * forward.y - right.y * forward.x
    };

    const float eyeX = nm_px;
    const float eyeY = nm_py + 162.0f;
    const float eyeZ = nm_pz;
    const float distance = nm_first_person ? 0.0f : 400.0f;

    const NmPoint cam{
        eyeX - forward.x * distance,
        eyeY - forward.y * distance,
        eyeZ - forward.z * distance
    };

    const NmPoint rel{p.x-cam.x, p.y-cam.y, p.z-cam.z};
    const float vx = rel.x*right.x + rel.y*right.y + rel.z*right.z;
    const float vy = rel.x*up.x + rel.y*up.y + rel.z*up.z;
    const float vz = rel.x*forward.x + rel.y*forward.y + rel.z*forward.z;

    if (vz <= NEAR_Z) return false;

    const float tanHalf = std::tan(FOV * deg * 0.5f);
    const float aspect = (float)d3d.current_width / (float)d3d.current_height;

    out.x = vx / (vz * tanHalf * aspect);
    out.y = vy / (vz * tanHalf);

    // SM64's normal camera frustum is 100..30000. gfx_direct3d11 reports a
    // 0..1 depth convention, so use the matching D3D perspective depth.
    out.z = FAR_Z / (FAR_Z - NEAR_Z)
          - (NEAR_Z * FAR_Z) / ((FAR_Z - NEAR_Z) * vz);
    if (out.z < 0.0f) out.z = 0.0f;
    if (out.z > 1.0f) out.z = 1.0f;

    out.r=r; out.g=g; out.b=b; out.a=a;
    return out.x > -2.5f && out.x < 2.5f
        && out.y > -2.5f && out.y < 2.5f;
}

static void nm_add_world_box(
    float cx, float cy, float cz,
    float sx, float sy, float sz,
    float r, float g, float b
) {
    const float hx=sx*0.5f, hy=sy*0.5f, hz=sz*0.5f;
    NmPoint p[8] = {
        {cx-hx,cy-hy,cz-hz},{cx+hx,cy-hy,cz-hz},
        {cx+hx,cy+hy,cz-hz},{cx-hx,cy+hy,cz-hz},
        {cx-hx,cy-hy,cz+hz},{cx+hx,cy-hy,cz+hz},
        {cx+hx,cy+hy,cz+hz},{cx-hx,cy+hy,cz+hz},
    };
    static const int faces[6][4] = {
        {0,1,2,3},{5,4,7,6},{4,0,3,7},
        {1,5,6,2},{3,2,6,7},{4,5,1,0}
    };

    for (int fi=0; fi<6; ++fi) {
        NmVertex q[4];
        bool ok=true;
        for (int k=0;k<4;++k) {
            if (!nm_project(p[faces[fi][k]], q[k], r,g,b,1.0f)) {
                ok=false;
                break;
            }
        }
        if (ok) nm_push_quad(nm_world_vertices,q[0],q[1],q[2],q[3]);
    }
}

static NmPoint nm_local_to_world(float lx, float ly, float lz) {
    const float a = nm_yaw * 0.01745329251994329577f;
    const float s = std::sin(a);
    const float c = std::cos(a);
    return NmPoint{
        nm_px + lx*c - lz*s,
        nm_py + ly,
        nm_pz + lx*s + lz*c
    };
}

static void nm_add_player_box(
    float cx, float cy, float cz,
    float sx, float sy, float sz,
    float r, float g, float b
) {
    const float hx=sx*0.5f, hy=sy*0.5f, hz=sz*0.5f;
    NmPoint p[8] = {
        nm_local_to_world(cx-hx,cy-hy,cz-hz),
        nm_local_to_world(cx+hx,cy-hy,cz-hz),
        nm_local_to_world(cx+hx,cy+hy,cz-hz),
        nm_local_to_world(cx-hx,cy+hy,cz-hz),
        nm_local_to_world(cx-hx,cy-hy,cz+hz),
        nm_local_to_world(cx+hx,cy-hy,cz+hz),
        nm_local_to_world(cx+hx,cy+hy,cz+hz),
        nm_local_to_world(cx-hx,cy+hy,cz+hz),
    };
    static const int faces[6][4] = {
        {0,1,2,3},{5,4,7,6},{4,0,3,7},
        {1,5,6,2},{3,2,6,7},{4,5,1,0}
    };

    for (int fi=0; fi<6; ++fi) {
        NmVertex q[4];
        bool ok=true;
        for (int k=0;k<4;++k) {
            if (!nm_project(p[faces[fi][k]], q[k], r,g,b,1.0f)) {
                ok=false;
                break;
            }
        }
        if (ok) nm_push_quad(nm_world_vertices,q[0],q[1],q[2],q[3]);
    }
}

static void nm_block_colour(int type, float &r, float &g, float &b) {
    r=0.45f; g=0.32f; b=0.18f;
    switch (type) {
        case 1: r=0.28f; g=0.62f; b=0.20f; break;
        case 2: r=0.52f; g=0.52f; b=0.52f; break;
        case 3: r=0.48f; g=0.30f; b=0.17f; break;
        case 4: r=0.70f; g=0.53f; b=0.31f; break;
        case 5: r=0.38f; g=0.38f; b=0.40f; break;
        case 6: r=0.55f; g=0.78f; b=0.82f; break;
        case 7: r=0.78f; g=0.12f; b=0.10f; break;
        case 8: r=0.90f; g=0.75f; b=0.25f; break;
        case 9: r=0.58f; g=0.20f; b=0.18f; break;
    }
}

static void nm_build_world() {
    const int count = native_minecraft_block_count();
    for (int i=0;i<count;++i) {
        int bx=0,by=0,bz=0,type=1;
        if (!native_minecraft_get_block(i,&bx,&by,&bz,&type)) continue;

        float r,g,b;
        nm_block_colour(type,r,g,b);
        nm_add_world_box(
            (bx+0.5f)*100.0f,
            (by+0.5f)*100.0f,
            (bz+0.5f)*100.0f,
            99.0f,99.0f,99.0f,
            r,g,b
        );
    }

    if (!nm_first_person) {
        // Blocky Steve proportions. Retail skin textures are intentionally not
        // embedded; a local asset converter can replace these colours later.
        nm_add_player_box(0,156,0,50,50,50, 0.72f,0.52f,0.36f);
        nm_add_player_box(0,111,0,60,70,30, 0.05f,0.55f,0.62f);
        nm_add_player_box(-18,48,0,27,90,28, 0.12f,0.20f,0.55f);
        nm_add_player_box( 18,48,0,27,90,28, 0.12f,0.20f,0.55f);
        nm_add_player_box(-44,108,0,24,74,24, 0.72f,0.52f,0.36f);
        nm_add_player_box( 44,108,0,24,74,24, 0.72f,0.52f,0.36f);
    }
}

static void nm_build_survival_hud() {
    const float sw=(float)d3d.current_width;
    const float sh=(float)d3d.current_height;
    const float slot=42.0f;
    const float total=slot*9.0f;
    const float x0=(sw-total)*0.5f;
    const float y=sh-slot-18.0f;

    for (int i=0;i<9;++i) {
        const float x=x0+i*slot;
        const bool selected=i==nm_slot;
        nm_push_rect_px(x,y,slot-2,slot-2,
            selected?0.88f:0.16f,
            selected?0.88f:0.16f,
            selected?0.88f:0.16f,
            0.88f);

        float r,g,b;
        nm_block_colour(i+1,r,g,b);
        nm_push_rect_px(x+6,y+6,slot-14,slot-14,r,g,b,1.0f);
    }

    // Placeholder survival meters; values become real native health/hunger in
    // the next gameplay module, but the layout already matches the final HUD.
    const float heartY=y-24.0f;
    for (int i=0;i<10;++i) {
        nm_push_rect_px(x0+i*18.0f,heartY,13.0f,13.0f,0.82f,0.08f,0.10f,0.96f);
        nm_push_rect_px(x0+total-13.0f-i*18.0f,heartY,13.0f,13.0f,0.76f,0.48f,0.10f,0.96f);
    }

    // Crosshair.
    nm_push_rect_px(sw*0.5f-1.0f,sh*0.5f-8.0f,2.0f,16.0f,1,1,1,0.95f);
    nm_push_rect_px(sw*0.5f-8.0f,sh*0.5f-1.0f,16.0f,2.0f,1,1,1,0.95f);

    if (nm_first_person && !nm_inventory) {
        // Blocky first-person arm/held-slot silhouette.
        nm_push_rect_ndc(0.50f,-1.03f,0.98f,-0.43f,0.72f,0.52f,0.36f,1.0f);
        float r,g,b;
        nm_block_colour(nm_slot+1,r,g,b);
        nm_push_rect_ndc(0.56f,-0.76f,0.88f,-0.48f,r,g,b,1.0f);
    }
}

static void nm_build_inventory() {
    if (!nm_inventory) return;

    nm_push_rect_ndc(-1,-1,1,1,0,0,0,0.42f);

    const float sw=(float)d3d.current_width;
    const float sh=(float)d3d.current_height;
    const float cell=52.0f;
    const float width=cell*9.0f+28.0f;
    const float height=cell*4.0f+42.0f;
    const float x0=(sw-width)*0.5f;
    const float y0=(sh-height)*0.5f;

    nm_push_rect_px(x0,y0,width,height,0.12f,0.12f,0.12f,0.96f);
    nm_push_rect_px(x0+6,y0+6,width-12,height-12,0.58f,0.58f,0.58f,0.96f);

    for (int row=0;row<4;++row) {
        for (int col=0;col<9;++col) {
            const float x=x0+14.0f+col*cell;
            const float y=y0+18.0f+row*cell;
            nm_push_rect_px(x,y,cell-6,cell-6,0.16f,0.16f,0.16f,0.98f);
            if (row==3) {
                float r,g,b;
                nm_block_colour(col+1,r,g,b);
                nm_push_rect_px(x+8,y+8,cell-22,cell-22,r,g,b,1.0f);
            }
        }
    }
}

static bool nm_init_pipeline() {
    if (nm_pipeline_ready) return true;

    static const char *shader = R"(
struct VSIn { float3 p:POSITION; float4 c:COLOR0; };
struct VSOut { float4 p:SV_POSITION; float4 c:COLOR0; };
VSOut VS(VSIn i) { VSOut o; o.p=float4(i.p,1); o.c=i.c; return o; }
float4 PS(VSOut i):SV_TARGET { return i.c; }
)";

    ComPtr<ID3DBlob> vsb, psb, err;
    if (FAILED(d3d.D3DCompile(
        shader,strlen(shader),"NativeMinecraft",nullptr,nullptr,
        "VS","vs_4_0_level_9_1",D3DCOMPILE_OPTIMIZATION_LEVEL2,0,
        vsb.GetAddressOf(),err.GetAddressOf()))) return false;

    err.Reset();
    if (FAILED(d3d.D3DCompile(
        shader,strlen(shader),"NativeMinecraft",nullptr,nullptr,
        "PS","ps_4_0_level_9_1",D3DCOMPILE_OPTIMIZATION_LEVEL2,0,
        psb.GetAddressOf(),err.GetAddressOf()))) return false;

    if (FAILED(d3d.device->CreateVertexShader(
        vsb->GetBufferPointer(),vsb->GetBufferSize(),nullptr,nm_vs.GetAddressOf()))) return false;
    if (FAILED(d3d.device->CreatePixelShader(
        psb->GetBufferPointer(),psb->GetBufferSize(),nullptr,nm_ps.GetAddressOf()))) return false;

    D3D11_INPUT_ELEMENT_DESC layout[] = {
        {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"COLOR",0,DXGI_FORMAT_R32G32B32A32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
    };
    if (FAILED(d3d.device->CreateInputLayout(
        layout,2,vsb->GetBufferPointer(),vsb->GetBufferSize(),nm_layout.GetAddressOf()))) return false;

    D3D11_BUFFER_DESC bd{};
    bd.ByteWidth=sizeof(NmVertex)*65536;
    bd.Usage=D3D11_USAGE_DYNAMIC;
    bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;
    bd.CPUAccessFlags=D3D11_CPU_ACCESS_WRITE;
    if (FAILED(d3d.device->CreateBuffer(&bd,nullptr,nm_vb.GetAddressOf()))) return false;

    D3D11_BLEND_DESC blend{};
    blend.RenderTarget[0].BlendEnable=TRUE;
    blend.RenderTarget[0].SrcBlend=D3D11_BLEND_SRC_ALPHA;
    blend.RenderTarget[0].DestBlend=D3D11_BLEND_INV_SRC_ALPHA;
    blend.RenderTarget[0].BlendOp=D3D11_BLEND_OP_ADD;
    blend.RenderTarget[0].SrcBlendAlpha=D3D11_BLEND_ONE;
    blend.RenderTarget[0].DestBlendAlpha=D3D11_BLEND_INV_SRC_ALPHA;
    blend.RenderTarget[0].BlendOpAlpha=D3D11_BLEND_OP_ADD;
    blend.RenderTarget[0].RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;
    if (FAILED(d3d.device->CreateBlendState(&blend,nm_alpha_blend.GetAddressOf()))) return false;

    D3D11_DEPTH_STENCIL_DESC worldDepth{};
    worldDepth.DepthEnable=TRUE;
    worldDepth.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ALL;
    worldDepth.DepthFunc=D3D11_COMPARISON_LESS_EQUAL;
    if (FAILED(d3d.device->CreateDepthStencilState(
        &worldDepth,nm_world_depth.GetAddressOf()))) return false;

    D3D11_DEPTH_STENCIL_DESC hudDepth{};
    hudDepth.DepthEnable=FALSE;
    hudDepth.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO;
    hudDepth.DepthFunc=D3D11_COMPARISON_ALWAYS;
    if (FAILED(d3d.device->CreateDepthStencilState(
        &hudDepth,nm_hud_depth.GetAddressOf()))) return false;

    D3D11_RASTERIZER_DESC rs{};
    rs.FillMode=D3D11_FILL_SOLID;
    rs.CullMode=D3D11_CULL_NONE;
    rs.DepthClipEnable=TRUE;
    if (FAILED(d3d.device->CreateRasterizerState(&rs,nm_no_cull.GetAddressOf()))) return false;

    nm_pipeline_ready=true;
    return true;
}

static void nm_draw_native_vertices(
    const std::vector<NmVertex> &vertices,
    bool depthTest,
    bool alphaBlend
) {
    if (vertices.empty() || vertices.size() > 65536) return;

    D3D11_MAPPED_SUBRESOURCE mapped{};
    if (FAILED(d3d.context->Map(
        nm_vb.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped))) return;

    memcpy(mapped.pData,vertices.data(),vertices.size()*sizeof(NmVertex));
    d3d.context->Unmap(nm_vb.Get(),0);

    UINT stride=sizeof(NmVertex), offset=0;
    ID3D11Buffer *buffer=nm_vb.Get();

    d3d.context->OMSetRenderTargets(
        1,
        d3d.backbuffer_view.GetAddressOf(),
        depthTest ? d3d.depth_stencil_view.Get() : nullptr
    );
    d3d.context->OMSetBlendState(
        alphaBlend ? nm_alpha_blend.Get() : nullptr,
        nullptr,0xFFFFFFFF
    );
    d3d.context->OMSetDepthStencilState(
        depthTest ? nm_world_depth.Get() : nm_hud_depth.Get(),0
    );
    d3d.context->RSSetState(nm_no_cull.Get());
    d3d.context->IASetInputLayout(nm_layout.Get());
    d3d.context->IASetVertexBuffers(0,1,&buffer,&stride,&offset);
    d3d.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    d3d.context->VSSetShader(nm_vs.Get(),nullptr,0);
    d3d.context->PSSetShader(nm_ps.Get(),nullptr,0);
    d3d.context->Draw((UINT)vertices.size(),0);
}

static void nm_render_native_minecraft() {
    if (!native_minecraft_active() || !nm_init_pipeline()) return;

    native_minecraft_get_render_state(
        &nm_px,&nm_py,&nm_pz,&nm_yaw,&nm_pitch,
        &nm_first_person,&nm_slot,&nm_inventory
    );

    nm_world_vertices.clear();
    nm_hud_vertices.clear();
    nm_world_vertices.reserve(16384);
    nm_hud_vertices.reserve(4096);

    nm_build_world();
    nm_build_survival_hud();
    nm_build_inventory();

    // World first: shares SM64's actual depth buffer.
    nm_draw_native_vertices(nm_world_vertices,true,false);

    // UI second: never depth-tested.
    nm_draw_native_vertices(nm_hud_vertices,false,true);

    // Direct D3D state changes bypass SM64's state cache. Force a clean
    // rebind next time the normal renderer draws.
    d3d.last_shader_program=nullptr;
    d3d.last_vertex_buffer_stride=0;
    d3d.last_blend_state.Reset();
    d3d.last_resource_views[0].Reset();
    d3d.last_resource_views[1].Reset();
    d3d.last_sampler_states[0].Reset();
    d3d.last_sampler_states[1].Reset();
    d3d.last_depth_test=-1;
    d3d.last_depth_mask=-1;
    d3d.last_zmode_decal=-1;
    d3d.last_primitive_topology=D3D_PRIMITIVE_TOPOLOGY_UNDEFINED;
}
