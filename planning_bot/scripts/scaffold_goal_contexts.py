#!/usr/bin/env python3
"""Add Obsidian callout scaffolds for goal mapping context fields."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from planning_bot.core.config import GOALS_FILE
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.goals_mapper import GoalsMapper


def _callout_lines() -> list[str]:
    return [line.rstrip() for line in pdmsg("goal_context_callout_lines").splitlines()]


def _is_goal_line(line: str) -> bool:
    return line.strip().startswith("- [ ]")


def _in_fenced_code_toggle(line: str, in_fence: bool) -> bool:
    if line.strip().startswith("```"):
        return not in_fence
    return in_fence


def _goal_block_end(lines: list[str], start_idx: int) -> int:
    in_fence = False
    for idx in range(start_idx + 1, len(lines)):
        line = lines[idx]
        in_fence = _in_fenced_code_toggle(line, in_fence)
        if in_fence:
            continue
        if line.strip() and line == line.lstrip() and (
            line.startswith(("- [", "##", "---"))
        ):
            return idx
    return len(lines)


def _has_context_fields(block: list[str]) -> bool:
    return any(GoalsMapper._parse_goal_context_line(line) for line in block)


def scaffold_goal_contexts(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    inserted = 0
    idx = 0
    in_fence = False

    while idx < len(lines):
        line = lines[idx]
        in_fence = _in_fenced_code_toggle(line, in_fence)
        out.append(line)

        if not in_fence and _is_goal_line(line):
            end = _goal_block_end(lines, idx)
            block = lines[idx + 1 : end]
            if not _has_context_fields(block):
                out.extend(_callout_lines())
                inserted += 1

        idx += 1

    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + suffix, inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goals-file", type=Path, default=GOALS_FILE)
    parser.add_argument("--check", action="store_true", help="Do not write; exit 1 if scaffolds are missing.")
    args = parser.parse_args()

    path = args.goals_file
    text = path.read_text(encoding="utf-8")
    updated, inserted = scaffold_goal_contexts(text)

    if args.check:
        print(f"missing_context_blocks={inserted}")
        return 1 if inserted else 0

    if inserted:
        path.write_text(updated, encoding="utf-8")
    print(f"inserted_context_blocks={inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
