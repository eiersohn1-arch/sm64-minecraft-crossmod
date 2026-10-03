#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

from sm64_collision import parse_collision, voxelize

ROOT = pathlib.Path(__file__).resolve().parents[1]
DECOMP = ROOT / "vendor" / "sm64-decomp"

AREAS = [
    {
        "id": "grounds",
        "collision": "levels/castle_grounds/areas/1/collision.inc.c",
        "offset": (0, 0, -260),
        "theme": "grounds",
    },
    {
        "id": "lobby",
        "collision": "levels/castle_inside/areas/1/collision.inc.c",
        "offset": (0, 0, 0),
        "theme": "castle",
    },
    {
        "id": "upper",
        "collision": "levels/castle_inside/areas/2/collision.inc.c",
        "offset": (260, 0, 0),
        "theme": "castle",
    },
    {
        "id": "basement",
        "collision": "levels/castle_inside/areas/3/collision.inc.c",
        "offset": (-260, 0, 0),
        "theme": "castle",
    },
    {
        "id": "courtyard",
        "collision": "levels/castle_courtyard/areas/1/collision.inc.c",
        "offset": (0, 0, 260),
        "theme": "courtyard",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a local Peach's Castle hub plan from SM64 collision data."
    )
    parser.add_argument(
        "--units-per-block",
        type=float,
        default=100.0,
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
    )
    return parser.parse_args()


def point(
    source: tuple[int, int, int],
    offset: tuple[int, int, int],
    scale: float,
) -> list[int]:
    x, y, z = source
    return [
        round(x / scale) + offset[0],
        round(y / scale) + offset[1],
        round(-z / scale) + offset[2],
    ]


def main() -> int:
    args = parse_args()
    if args.units_per_block <= 0:
        print("ERROR: --units-per-block must be greater than zero.")
        return 2

    all_blocks: dict[tuple[int, int, int], str] = {}
    stats: list[dict] = []
    offsets = {area["id"]: area["offset"] for area in AREAS}

    for area in AREAS:
        source = DECOMP / area["collision"]
        if not source.is_file():
            print(f"ERROR: missing castle source: {source}")
            print("Run: python tools/bootstrap_sources.py")
            return 3

        mesh = parse_collision(source)
        blocks = voxelize(
            mesh,
            units_per_block=args.units_per_block,
            theme=area["theme"],
        )

        ox, oy, oz = area["offset"]
        for (x, y, z), block in blocks.items():
            all_blocks[(x + ox, y + oy, z + oz)] = block

        stats.append({
            "id": area["id"],
            "vertices": len(mesh.vertices),
            "triangles": len(mesh.triangles),
            "blocks": len(blocks),
            "offset": list(area["offset"]),
        })

        print(
            f"{area['id']}: {len(mesh.vertices)} vertices, "
            f"{len(mesh.triangles)} triangles, {len(blocks)} blocks"
        )

    palette = sorted(set(all_blocks.values()))
    palette_index = {name: index for index, name in enumerate(palette)}

    grounds = offsets["grounds"]
    lobby = offsets["lobby"]
    upper = offsets["upper"]
    basement = offsets["basement"]
    courtyard = offsets["courtyard"]

    spawn = point((-1328, 260, 4664), grounds, args.units_per_block)
    lobby_spawn = point((-1023, 0, 1152), lobby, args.units_per_block)

    warps = [
        {
            "id": "grounds_to_lobby",
            "from": point((0, 800, -2800), grounds, args.units_per_block),
            "to": point((-1024, 512, -650), lobby, args.units_per_block),
        },
        {
            "id": "lobby_to_grounds",
            "from": point((-1024, 512, -650), lobby, args.units_per_block),
            "to": point((0, 800, -2500), grounds, args.units_per_block),
        },
        {
            "id": "lobby_to_upper",
            "from": point((-1023, 512, -1074), lobby, args.units_per_block),
            "to": point((-1023, 512, 3021), upper, args.units_per_block),
        },
        {
            "id": "upper_to_lobby",
            "from": point((-1023, 512, 3021), upper, args.units_per_block),
            "to": point((-1023, 512, -900), lobby, args.units_per_block),
        },
        {
            "id": "lobby_to_basement",
            "from": point((-1023, -1074, 922), lobby, args.units_per_block),
            "to": point((-1023, -1074, 922), basement, args.units_per_block),
        },
        {
            "id": "basement_to_lobby",
            "from": point((-1023, -1074, 922), basement, args.units_per_block),
            "to": point((-1023, -900, 700), lobby, args.units_per_block),
        },
        {
            "id": "lobby_to_courtyard",
            "from": point((-1024, 0, 3400), lobby, args.units_per_block),
            "to": point((-14, 0, -201), courtyard, args.units_per_block),
        },
        {
            "id": "courtyard_to_lobby",
            "from": point((-14, 0, -201), courtyard, args.units_per_block),
            "to": point((-1024, 0, 3150), lobby, args.units_per_block),
        },
    ]

    star_doors = [
        {
            "id": "eight_star_door",
            "required": 8,
            "pos": point((-2652, 512, -1463), lobby, args.units_per_block),
        },
        {
            "id": "thirty_star_door",
            "required": 30,
            "pos": point((307, -1074, 1997), basement, args.units_per_block),
        },
        {
            "id": "fifty_star_door",
            "required": 50,
            "pos": point((-204, 2253, 4762), upper, args.units_per_block),
        },
        {
            "id": "seventy_star_door",
            "required": 70,
            "pos": point((-204, 3174, 3772), upper, args.units_per_block),
        },
    ]

    bob_painting = point((-5422, 717, -461), lobby, args.units_per_block)

    output = args.output
    if output is None:
        output = (
            ROOT
            / "run"
            / "config"
            / "sm64cross"
            / "imported"
            / "hub"
            / "peachs_castle.json"
        )
    elif not output.is_absolute():
        output = ROOT / output

    data = {
        "format": "sm64cross-hub-v1",
        "unitsPerBlock": args.units_per_block,
        "areas": stats,
        "spawn": spawn,
        "lobbySpawn": lobby_spawn,
        "bobPainting": bob_painting,
        "warps": warps,
        "starDoors": star_doors,
        "palette": palette,
        "blocks": [
            [x, y, z, palette_index[block]]
            for (x, y, z), block in sorted(
                all_blocks.items(),
                key=lambda item: (item[0][1], item[0][0], item[0][2]),
            )
        ],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")

    print(f"Peach's Castle total blocks: {len(all_blocks)}")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
