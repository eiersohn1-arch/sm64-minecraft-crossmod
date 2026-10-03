#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import math
import pathlib
import re

VERTEX_RE = re.compile(
    r"\bCOL_VERTEX\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)"
)
TRI_INIT_RE = re.compile(
    r"\bCOL_TRI_INIT\(\s*([A-Z0-9_]+)\s*,\s*(?:0x[0-9A-Fa-f]+|\d+)\s*\)"
)
TRI_RE = re.compile(
    r"\bCOL_TRI\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)"
)


@dataclass(frozen=True)
class Vertex:
    x: int
    y: int
    z: int


@dataclass(frozen=True)
class Triangle:
    a: int
    b: int
    c: int
    surface: str


@dataclass(frozen=True)
class CollisionMesh:
    vertices: tuple[Vertex, ...]
    triangles: tuple[Triangle, ...]


def parse_collision(path: pathlib.Path) -> CollisionMesh:
    text = path.read_text(encoding="utf-8")
    vertices = tuple(
        Vertex(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        for match in VERTEX_RE.finditer(text)
    )

    triangles: list[Triangle] = []
    surface = "SURFACE_DEFAULT"

    for raw_line in text.splitlines():
        init = TRI_INIT_RE.search(raw_line)
        if init:
            surface = init.group(1)
            continue

        tri = TRI_RE.search(raw_line)
        if tri:
            a, b, c = (int(tri.group(i)) for i in range(1, 4))
            if max(a, b, c) >= len(vertices):
                raise ValueError(
                    f"Triangle references missing vertex in {path}: {(a, b, c)} "
                    f"with {len(vertices)} vertices"
                )
            triangles.append(Triangle(a, b, c, surface))

    if not vertices:
        raise ValueError(f"No COL_VERTEX entries found in {path}")
    if not triangles:
        raise ValueError(f"No COL_TRI entries found in {path}")

    return CollisionMesh(vertices=vertices, triangles=tuple(triangles))


def to_minecraft(vertex: Vertex, units_per_block: float) -> tuple[float, float, float]:
    return (
        vertex.x / units_per_block,
        vertex.y / units_per_block,
        -vertex.z / units_per_block,
    )


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(
        (a[0] - b[0]) ** 2
        + (a[1] - b[1]) ** 2
        + (a[2] - b[2]) ** 2
    )


def _normal_y(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> float:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    nx = ab[1] * ac[2] - ab[2] * ac[1]
    ny = ab[2] * ac[0] - ab[0] * ac[2]
    nz = ab[0] * ac[1] - ab[1] * ac[0]
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return 0.0 if length == 0 else abs(ny / length)


def block_for_surface(surface: str, normal_y: float, theme: str) -> str:
    slippery = "SLIPPERY" in surface

    if theme == "castle":
        if slippery:
            return "minecraft:polished_diorite"
        if surface == "SURFACE_HANGABLE":
            return "minecraft:oak_planks"
        if normal_y < 0.42:
            return "minecraft:white_concrete"
        return "minecraft:polished_diorite"

    if theme == "courtyard":
        if slippery:
            return "minecraft:polished_diorite"
        if normal_y < 0.42:
            return "minecraft:stone_bricks"
        return "minecraft:mossy_stone_bricks"

    if theme == "grounds":
        if slippery:
            return "minecraft:packed_ice"
        if normal_y < 0.42:
            return "minecraft:stone_bricks"
        return "minecraft:grass_block"

    if slippery:
        return "minecraft:packed_ice"
    if surface == "SURFACE_HANGABLE":
        return "minecraft:oak_planks"
    if normal_y < 0.42:
        return "minecraft:stone"
    return "minecraft:grass_block"


def voxelize(
    mesh: CollisionMesh,
    *,
    units_per_block: float = 100.0,
    sample_spacing: float = 0.72,
    max_steps: int = 192,
    theme: str = "outdoor",
) -> dict[tuple[int, int, int], str]:
    blocks: dict[tuple[int, int, int], str] = {}

    for tri in mesh.triangles:
        a = to_minecraft(mesh.vertices[tri.a], units_per_block)
        b = to_minecraft(mesh.vertices[tri.b], units_per_block)
        c = to_minecraft(mesh.vertices[tri.c], units_per_block)

        longest = max(_distance(a, b), _distance(b, c), _distance(c, a))
        steps = max(1, min(max_steps, math.ceil(longest / sample_spacing)))
        block = block_for_surface(tri.surface, _normal_y(a, b, c), theme)

        for i in range(steps + 1):
            u = i / steps
            remaining = steps - i

            for j in range(remaining + 1):
                v = j / steps
                w = 1.0 - u - v
                x = round(a[0] * w + b[0] * u + c[0] * v)
                y = round(a[1] * w + b[1] * u + c[1] * v)
                z = round(a[2] * w + b[2] * u + c[2] * v)

                key = (x, y, z)
                previous = blocks.get(key)
                if previous is None or previous == "minecraft:grass_block":
                    blocks[key] = block

    return blocks
