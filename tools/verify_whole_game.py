#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

EXPECTED_LEVEL_DIRS = {
    "bbh", "bitdw", "bitfs", "bits", "bob",
    "bowser_1", "bowser_2", "bowser_3",
    "castle_courtyard", "castle_grounds", "castle_inside",
    "ccm", "cotmc", "ddd", "ending", "hmc", "intro", "jrb",
    "lll", "menu", "pss", "rr", "sa", "sl", "ssl", "thi",
    "totwc", "ttc", "ttm", "vcutm", "wdw", "wf", "wmotr",
}

PROTECTED_FILES = {
    "src/game/level_update.c",
    "src/game/save_file.c",
    "src/game/star_select.c",
    "data/behavior_data.c",
    "levels/course_defines.h",
}


def run_text(args: list[str], cwd: pathlib.Path) -> str:
    return subprocess.check_output(
        args,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def verify(sm64: pathlib.Path) -> None:
    levels = sm64 / "levels"
    actual = {p.name for p in levels.iterdir() if p.is_dir()}

    missing = sorted(EXPECTED_LEVEL_DIRS - actual)
    if missing:
        raise RuntimeError("Missing SM64 level directories: " + ", ".join(missing))

    for level in sorted(EXPECTED_LEVEL_DIRS):
        script = levels / level / "script.c"
        if not script.is_file():
            raise RuntimeError(f"Missing level script: {script}")

    course_defines = (levels / "course_defines.h").read_text(encoding="utf-8")

    before_bonus = course_defines.split("DEFINE_COURSES_END()", 1)[0]
    main_courses = re.findall(r"DEFINE_COURSE\(COURSE_([A-Z0-9_]+),", before_bonus)
    main_courses = [name for name in main_courses if name != "NONE"]

    bonus_courses = re.findall(
        r"DEFINE_BONUS_COURSE\(COURSE_([A-Z0-9_]+),",
        course_defines,
    )

    if len(main_courses) != 15:
        raise RuntimeError(
            f"Expected 15 main SM64 courses, found {len(main_courses)}: {main_courses}"
        )

    if len(bonus_courses) != 10:
        raise RuntimeError(
            f"Expected 10 SM64 bonus/end course entries, found {len(bonus_courses)}: {bonus_courses}"
        )

    changed = set(
        line.strip()
        for line in run_text(["git", "diff", "--name-only"], sm64).splitlines()
        if line.strip()
    )

    bad = sorted(
        path for path in changed
        if path.startswith("levels/")
        or path in PROTECTED_FILES
    )

    if bad:
        raise RuntimeError(
            "Whole-game invariant broken: crossmod modified original "
            "level/progression files: " + ", ".join(bad)
        )

    print("WHOLE GAME CHECK OK")
    print("15 main courses preserved")
    print("10 bonus/end course entries preserved")
    print(f"{len(EXPECTED_LEVEL_DIRS)} original level directories preserved")
    print("Original level scripts, star select, save data and level progression are untouched")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sm64-port", type=pathlib.Path, required=True)
    args = parser.parse_args()

    try:
        verify(args.sm64_port.resolve())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
