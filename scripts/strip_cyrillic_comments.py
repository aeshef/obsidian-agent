#!/usr/bin/env python3
"""Remove # comment lines that contain Cyrillic (runtime .py only)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CYR = re.compile(f"[{chr(0x400)}-{chr(0x4FF)}]")
SKIP = {"venv", ".venv", "__pycache__", ".git", "tests", "migration"}
SKIP_PARTS = ("knowledge_bot/tools", "planning_bot/scripts")


def strip_file(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("#") and _CYR.search(line):
            removed += 1
            i += 1
            continue
        # module docstring line with only cyrillic explanation - skip single-line
        if (
            i == 0
            and (stripped.startswith('"""') or stripped.startswith("'''"))
            and _CYR.search(line)
            and stripped.count('"""') >= 2
        ):
            removed += 1
            i += 1
            continue
        out.append(line)
        i += 1
    if removed:
        path.write_text("".join(out), encoding="utf-8")
    return removed


def main() -> int:
    total = 0
    targets = sys.argv[1:]
    if not targets:
        for p in sorted(ROOT.rglob("*.py")):
            if any(x in p.parts for x in SKIP) or p.name.startswith(".scrub_"):
                continue
            rel = p.relative_to(ROOT).as_posix()
            if any(x in rel for x in SKIP_PARTS) or rel.startswith("scripts/"):
                continue
            if "knowledge_bot" not in rel and "shared" not in rel:
                continue
            n = strip_file(p)
            if n:
                print(f"{rel}: removed {n} comment lines")
                total += n
    else:
        for rel in targets:
            total += strip_file(ROOT / rel)
    print("total_removed", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
