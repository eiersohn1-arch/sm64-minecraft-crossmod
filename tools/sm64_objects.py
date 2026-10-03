#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re

COMMENT_RE = re.compile(r"/\*.*?\*/")
STAR_INDEX_RE = re.compile(r"STAR_INDEX_ACT_(\d+)")
MACRO_STAR_RE = re.compile(r"macro_box_star_act_(\d+)")


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
            entry = {
                "model": args[0],
                "pos": (int(args[1], 0), int(args[2], 0), int(args[3], 0)),
                "bhvParam": args[7],
                "behavior": args[8],
                "acts": args[9] if len(args) > 9 else "ALL_ACTS",
            }
        except ValueError:
            continue

        result.append(entry)

    return result


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
            "bhvStar": "static",
        }.get(behavior, "scripted")

        objectives[index] = {
            "index": index,
            "id": f"bob_omb_battlefield:{index}",
            "kind": kind,
            "pos": obj["pos"],
            "source": behavior,
        }

    red_coins: list[tuple[int, int, int]] = []
    hidden_triggers: list[tuple[int, int, int]] = []

    for obj in macros:
        preset = obj["preset"]

        if preset == "macro_red_coin":
            red_coins.append(obj["pos"])
            continue

        if preset == "macro_hidden_star_trigger":
            hidden_triggers.append(obj["pos"])
            continue

        star_match = MACRO_STAR_RE.fullmatch(preset)
        if star_match:
            index = int(star_match.group(1))
            objectives[index] = {
                "index": index,
                "id": f"bob_omb_battlefield:{index}",
                "kind": "breakable_box",
                "pos": obj["pos"],
                "source": preset,
            }

    if 5 in objectives:
        objectives[5]["triggerPositions"] = hidden_triggers

    return {
        "objectives": [objectives[index] for index in sorted(objectives)],
        "redCoins": red_coins,
    }
