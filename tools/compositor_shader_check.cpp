#include <windows.h>
#include <d3dcompiler.h>

#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>

static bool compile(
        const std::string &source,
        const char *entry,
        const char *profile
) {
    ID3DBlob *code = nullptr;
    ID3DBlob *errors = nullptr;

    HRESULT hr = D3DCompile(
        source.data(),
        source.size(),
        "sm64cross-compositor-smoke",
        nullptr,
        nullptr,
        entry,
        profile,
        D3DCOMPILE_OPTIMIZATION_LEVEL2,
        0,
        &code,
        &errors
    );

    if (FAILED(hr)) {
        std::fprintf(
            stderr,
            "D3DCompile failed for %s/%s\n",
            entry,
            profile
        );

        if (errors != nullptr) {
            std::fwrite(
                errors->GetBufferPointer(),
                1,
                errors->GetBufferSize(),
                stderr
            );
        }

        if (errors != nullptr) errors->Release();
        if (code != nullptr) code->Release();
        return false;
    }

    if (errors != nullptr) errors->Release();
    if (code != nullptr) code->Release();

    std::printf("OK %s %s\n", entry, profile);
    return true;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        std::fprintf(stderr, "usage: shader_check <file.hlsl>\n");
        return 2;
    }

    std::ifstream input(argv[1], std::ios::binary);
    if (!input) {
        std::fprintf(stderr, "cannot open %s\n", argv[1]);
        return 2;
    }

    std::string source(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>()
    );

    bool ok =
        compile(source, "VSMain", "vs_4_0")
        && compile(source, "PSMain", "ps_4_0");

    return ok ? 0 : 1;
}
