#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from sm64_collision import parse_collision, voxelize
from sm64_objects import extract_bob_objectives

ROOT = pathlib.Path(__file__).resolve().parents[1]
DECOMP = ROOT / "vendor" / "sm64-decomp"

COURSES = {
    "bob_omb_battlefield": {
        "collision": "levels/bob/areas/1/collision.inc.c",
        "script": "levels/bob/script.c",
        "macro": "levels/bob/areas/1/macro.inc.c",
        "spawn_sm64": (-6558, 0, 6464),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert SM64 decomp course data into a local Minecraft block plan."
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


def transform_objective(objective: dict, scale: float) -> dict:
    transformed = dict(objective)
    transformed["pos"] = transform_point(objective["pos"], scale)

    if "triggerPositions" in objective:
        transformed["triggerPositions"] = [
            transform_point(position, scale)
            for position in objective["triggerPositions"]
        ]

    return transformed


def main() -> int:
    args = parse_args()
    spec = COURSES[args.course]
    collision_source = DECOMP / spec["collision"]
    script_source = DECOMP / spec["script"]
    macro_source = DECOMP / spec["macro"]

    required = [collision_source, script_source, macro_source]
    missing = [path for path in required if not path.is_file()]
    if missing:
        print("ERROR: missing SM64 decomp source files:")
        for path in missing:
            print(f"  {path}")
        print("Run: python tools/bootstrap_sources.py")
        return 2

    if args.units_per_block <= 0:
        print("ERROR: --units-per-block must be greater than zero.")
        return 3

    print(f"Reading {collision_source.relative_to(ROOT)} ...")
    mesh = parse_collision(collision_source)
    print(f"Parsed {len(mesh.vertices)} vertices and {len(mesh.triangles)} triangles.")

    blocks = voxelize(mesh, units_per_block=args.units_per_block)
    print(f"Voxelized to {len(blocks)} unique Minecraft blocks.")

    mission_data = extract_bob_objectives(script_source, macro_source)
    objectives = [
        transform_objective(objective, args.units_per_block)
        for objective in mission_data["objectives"]
    ]
    red_coins = [
        transform_point(position, args.units_per_block)
        for position in mission_data["redCoins"]
    ]

    print(
        f"Parsed {len(objectives)} star objectives and "
        f"{len(red_coins)} red coin positions."
    )

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
        "sources": {
            "collision": spec["collision"],
            "script": spec["script"],
            "macro": spec["macro"],
        },
        "unitsPerBlock": args.units_per_block,
        "sourceStats": {
            "vertices": len(mesh.vertices),
            "triangles": len(mesh.triangles),
            "objectives": len(objectives),
            "redCoins": len(red_coins),
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
        "objectives": objectives,
        "redCoins": red_coins,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")

    print(f"Wrote {output}")
    print("This generated plan is local and gitignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
