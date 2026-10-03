#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from sm64_collision import parse_collision, voxelize

ROOT = pathlib.Path(__file__).resolve().parents[1]
DECOMP = ROOT / "vendor" / "sm64-decomp"

COURSES = {
    "bob_omb_battlefield": {
        "collision": "levels/bob/areas/1/collision.inc.c",
        "spawn_sm64": (-6558, 0, 6464),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert SM64 decomp collision into a local Minecraft block plan."
    )
    parser.add_argument("course", choices=sorted(COURSES))
    parser.add_argument(
        "--units-per-block",
        type=float,
        default=100.0,
        help="SM64 coordinate units per Minecraft block (default: 100).",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help="Output JSON. Defaults to the dev client's run/config directory.",
    )
    return parser.parse_args()


def transform_point(point: tuple[int, int, int], scale: float) -> list[int]:
    x, y, z = point
    return [round(x / scale), round(y / scale), round(-z / scale)]


def main() -> int:
    args = parse_args()
    spec = COURSES[args.course]
    source = DECOMP / spec["collision"]

    if not source.is_file():
        print(f"ERROR: missing decomp collision file: {source}")
        print("Run: python tools/bootstrap_sources.py")
        return 2

    if args.units_per_block <= 0:
        print("ERROR: --units-per-block must be greater than zero.")
        return 3

    print(f"Reading {source.relative_to(ROOT)} ...")
    mesh = parse_collision(source)
    print(f"Parsed {len(mesh.vertices)} vertices and {len(mesh.triangles)} triangles.")

    blocks = voxelize(mesh, units_per_block=args.units_per_block)
    print(f"Voxelized to {len(blocks)} unique Minecraft blocks.")

    palette = sorted(set(blocks.values()))
    palette_index = {name: index for index, name in enumerate(palette)}

    output = args.output
    if output is None:
        output = (
            ROOT
            / "run"
            / "config"
            / "sm64cross"
            / "imported"
            / "courses"
            / f"{args.course}.json"
        )
    elif not output.is_absolute():
        output = ROOT / output

    data = {
        "format": "sm64cross-blockplan-v1",
        "course": args.course,
        "source": spec["collision"],
        "unitsPerBlock": args.units_per_block,
        "sourceStats": {
            "vertices": len(mesh.vertices),
            "triangles": len(mesh.triangles),
        },
        "spawn": transform_point(spec["spawn_sm64"], args.units_per_block),
        "palette": palette,
        "blocks": [
            [x, y, z, palette_index[block]]
            for (x, y, z), block in sorted(
                blocks.items(),
                key=lambda item: (item[0][1], item[0][0], item[0][2]),
            )
        ],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")

    print(f"Wrote {output}")
    print("This generated plan is local and gitignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
