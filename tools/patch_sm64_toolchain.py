#!/usr/bin/env python3
"""Compatibility patch for sm64-port's bundled armips on current MinGW/GCC."""
from pathlib import Path
import argparse

def patch(sm64: Path) -> None:
    armips = sm64 / "tools" / "armips.cpp"
    if not armips.is_file():
        raise SystemExit(f"Bundled armips source missing: {armips}")

    text = armips.read_text(encoding="utf-8")

    if "#include <cstdint>\n#include <cstdio>" not in text:
        if "#include <cstdio>" not in text:
            raise SystemExit("Could not patch armips: <cstdio> marker missing.")
        text = text.replace(
            "#include <cstdio>",
            "#include <cstdint>\n#include <cstdio>",
            1,
        )

    text = text.replace(
        "GetFileAttributesEx(fileName.c_str(),GetFileExInfoStandard,&attr)",
        "GetFileAttributesExW(fileName.c_str(),GetFileExInfoStandard,&attr)",
    )
    text = text.replace(
        "GetFileAttributes(strFilename.c_str())",
        "GetFileAttributesW(strFilename.c_str())",
    )

    # New MinGW/GCC toolchains can fail to wire armips' wmain() entry point
    # through -municode and end up looking for WinMain instead.  Keep wmain()
    # as armips' real implementation, but expose the existing argv->wargv
    # wrapper as an ordinary main() on Windows too, then do not rely on
    # MinGW's Unicode CRT startup selection.
    guarded_main = """#ifndef _WIN32

int main(int argc, char* argv[])
{
	// convert input to wstring
	std::vector<std::wstring> wideStrings;
	for (int i = 0; i < argc; i++)
	{
		std::wstring str = convertUtf8ToWString(argv[i]);
		wideStrings.push_back(str);
	}

	// create argv replacement
	wchar_t** wargv = new wchar_t*[argc];
	for (int i = 0; i < argc; i++)
	{
		wargv[i] = (wchar_t*) wideStrings[i].c_str();
	}

	int result = wmain(argc,wargv);

	delete[] wargv;
	return result;
}

#endif
"""
    unguarded_main = guarded_main.replace("#ifndef _WIN32\n\n", "", 1).replace("\n#endif\n", "\n", 1)
    if guarded_main in text:
        text = text.replace(guarded_main, unguarded_main, 1)

    armips.write_text(text, encoding="utf-8")

    tools_makefile = sm64 / "tools" / "Makefile"
    make = tools_makefile.read_text(encoding="utf-8")
    make = make.replace(
        "ifeq ($(HOST_ENV),MinGW)\n  armips_LDFLAGS += -municode\nendif\n",
        "",
    )
    tools_makefile.write_text(make, encoding="utf-8")
    print("Patched bundled armips for current MinGW/GCC.")

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--sm64", default="vendor/sm64-port")
    args=parser.parse_args()
    patch(Path(args.sm64))
