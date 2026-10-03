#!/usr/bin/env python3
from __future__ import annotations

import math
import pathlib
import re

COMMENT_RE = re.compile(r"/\*.*?\*/")
STAR_INDEX_RE = re.compile(r"STAR_INDEX_ACT_(\d+)")
MACRO_STAR_RE = re.compile(r"macro_box_star_act_(\d+)")

MISSION_NAMES = {
    1: "Big Bob-omb on the Summit",
    2: "Footrace with Koopa the Quick",
    3: "Shoot to the Island in the Sky",
    4: "Find the 8 Red Coins",
    5: "Mario Wings to the Sky",
    6: "Behind Chain Chomp's Gate",
    7: "100 Coins",
}


def strip_comments(line: str) -> str:
    return COMMENT_RE.sub("", line)


def split_args(raw: str) -> list[str]:
    args: list[str] = []
    start = 0
    depth = 0

    for index, char in enumerate(raw):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(raw[start:index].strip())
            start = index + 1

    tail = raw[start:].strip()
    if tail:
        args.append(tail)
    return args


def macro_objects(path: pathlib.Path) -> list[dict]:
    result: list[dict] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = strip_comments(raw_line).strip()
        if not line.startswith("MACRO_OBJECT"):
            continue
        if line.startswith("MACRO_OBJECT_END"):
            continue

        open_paren = line.find("(")
        close_paren = line.rfind(")")
        if open_paren < 0 or close_paren < 0:
            continue

        args = split_args(line[open_paren + 1:close_paren])
        if len(args) < 5:
            continue

        try:
            result.append({
                "preset": args[0],
                "yaw": int(args[1], 0),
                "pos": (int(args[2], 0), int(args[3], 0), int(args[4], 0)),
                "bhvParam": args[5] if len(args) > 5 else None,
            })
        except ValueError:
            continue

    return result


def level_objects(path: pathlib.Path) -> list[dict]:
    result: list[dict] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = strip_comments(raw_line).strip()
        if not (line.startswith("OBJECT(") or line.startswith("OBJECT_WITH_ACTS(")):
            continue

        open_paren = line.find("(")
        close_paren = line.rfind(")")
        if open_paren < 0 or close_paren < 0:
            continue

        args = split_args(line[open_paren + 1:close_paren])
        if len(args) < 9:
            continue

        try:
            result.append({
                "model": args[0],
                "pos": (int(args[1], 0), int(args[2], 0), int(args[3], 0)),
                "bhvParam": args[7],
                "behavior": args[8],
                "acts": args[9] if len(args) > 9 else "ALL_ACTS",
            })
        except ValueError:
            continue

    return result


def _offset(
    pos: tuple[int, int, int],
    dx: float,
    dy: float,
    dz: float,
) -> tuple[int, int, int]:
    return (
        round(pos[0] + dx),
        round(pos[1] + dy),
        round(pos[2] + dz),
    )


def _line_coins(obj: dict, count: int = 5, spacing: float = 160.0) -> list[tuple[int, int, int]]:
    yaw = math.radians(obj["yaw"])
    direction = (math.sin(yaw), 0.0, math.cos(yaw))
    middle = (count - 1) / 2.0
    return [
        _offset(
            obj["pos"],
            direction[0] * (index - middle) * spacing,
            0,
            direction[2] * (index - middle) * spacing,
        )
        for index in range(count)
    ]


def _horizontal_ring(obj: dict, count: int = 8, radius: float = 300.0) -> list[tuple[int, int, int]]:
    return [
        _offset(
            obj["pos"],
            math.cos(index * math.tau / count) * radius,
            0,
            math.sin(index * math.tau / count) * radius,
        )
        for index in range(count)
    ]


def _vertical_ring(obj: dict, count: int = 8, radius: float = 280.0) -> list[tuple[int, int, int]]:
    yaw = math.radians(obj["yaw"])
    right = (math.cos(yaw), 0.0, -math.sin(yaw))
    result: list[tuple[int, int, int]] = []

    for index in range(count):
        angle = index * math.tau / count
        horizontal = math.cos(angle) * radius
        vertical = math.sin(angle) * radius
        result.append(_offset(
            obj["pos"],
            right[0] * horizontal,
            vertical,
            right[2] * horizontal,
        ))

    return result


def build_coin_markers(macros: list[dict]) -> list[tuple[int, int, int]]:
    coins: list[tuple[int, int, int]] = []

    for obj in macros:
        preset = obj["preset"]

        if preset in {"macro_yellow_coin_1", "macro_yellow_coin_2"}:
            coins.append(obj["pos"])
        elif preset == "macro_coin_line_horizontal":
            coins.extend(_line_coins(obj))
        elif preset == "macro_coin_ring_horizontal":
            coins.extend(_horizontal_ring(obj))
        elif preset == "macro_coin_ring_vertical_flying":
            coins.extend(_vertical_ring(obj))
        elif preset == "macro_breakable_box_three_coins":
            coins.extend([
                _offset(obj["pos"], -100, 0, 0),
                obj["pos"],
                _offset(obj["pos"], 100, 0, 0),
            ])
        elif preset in {"macro_bobomb", "macro_bobomb_stationary", "macro_goomba"}:
            coins.append(obj["pos"])
        elif preset == "macro_goomba_triplet_spawner":
            coins.extend([
                _offset(obj["pos"], -140, 0, 0),
                obj["pos"],
                _offset(obj["pos"], 140, 0, 0),
            ])

    # Preserve insertion order while removing exact duplicates.
    return list(dict.fromkeys(coins))


def extract_bob_objectives(
    script_path: pathlib.Path,
    macro_path: pathlib.Path,
) -> dict:
    objects = level_objects(script_path)
    macros = macro_objects(macro_path)

    objectives: dict[int, dict] = {}

    for obj in objects:
        star_match = STAR_INDEX_RE.search(obj["bhvParam"])
        if not star_match:
            continue

        index = int(star_match.group(1))
        behavior = obj["behavior"]

        kind = {
            "bhvKingBobomb": "boss",
            "bhvKoopa": "race",
            "bhvHiddenRedCoinStar": "red_coins",
            "bhvHiddenStar": "hidden_triggers",
            "bhvStar": "chain_chomp" if index == 6 else "static",
        }.get(behavior, "scripted")

        objectives[index] = {
            "index": index,
            "id": f"bob_omb_battlefield:{index}",
            "name": MISSION_NAMES.get(index, f"Star {index}"),
            "kind": kind,
            "pos": obj["pos"],
            "source": behavior,
        }

    race_endpoint = next(
        (obj["pos"] for obj in objects if obj["behavior"] == "bhvKoopaRaceEndpoint"),
        None,
    )

    red_coins: list[tuple[int, int, int]] = []
    hidden_triggers: list[tuple[int, int, int]] = []
    chain_chomp_pos: tuple[int, int, int] | None = None

    for obj in macros:
        preset = obj["preset"]

        if preset == "macro_red_coin":
            red_coins.append(obj["pos"])
            continue

        if preset == "macro_hidden_star_trigger":
            hidden_triggers.append(obj["pos"])
            continue

        if preset == "macro_chain_chomp":
            chain_chomp_pos = obj["pos"]
            continue

        star_match = MACRO_STAR_RE.fullmatch(preset)
        if star_match:
            index = int(star_match.group(1))
            objectives[index] = {
                "index": index,
                "id": f"bob_omb_battlefield:{index}",
                "name": MISSION_NAMES.get(index, f"Star {index}"),
                "kind": "breakable_box",
                "pos": obj["pos"],
                "source": preset,
            }

    if 2 in objectives and race_endpoint is not None:
        objectives[2]["finishPos"] = race_endpoint

    if 5 in objectives:
        objectives[5]["triggerPositions"] = hidden_triggers

    if 6 in objectives and chain_chomp_pos is not None:
        objectives[6]["triggerPositions"] = [chain_chomp_pos]

    objectives[7] = {
        "index": 7,
        "id": "bob_omb_battlefield:7",
        "name": MISSION_NAMES[7],
        "kind": "coins_100",
        "pos": (0, 0, 0),
        "source": "course_coin_total",
    }

    return {
        "objectives": [objectives[index] for index in sorted(objectives)],
        "redCoins": red_coins,
        "coinMarkers": build_coin_markers(macros),
    }
