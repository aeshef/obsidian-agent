#!/usr/bin/env python3
"""Move pdmsg import after __future__ and remove stray English docstring literals."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDMSG = "from planning_bot.core.pdmsg import pdmsg\n"
STRAY = re.compile(
    r"^'(?:Planning bot module\.|Operation implementation\.)'\s*\n",
    re.MULTILINE,
)


def fix(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    orig = src
    src = STRAY.sub("", src)
    if PDMSG.strip() not in src:
        return False
    lines = src.splitlines(keepends=True)
    pdmsg_idx = next((i for i, l in enumerate(lines) if l.strip() == PDMSG.strip()), None)
    if pdmsg_idx is None:
        return False
    if pdmsg_idx == 0 or (
        pdmsg_idx <= 2 and any("__future__" in lines[i] for i in range(len(lines)))
    ):
        # pdmsg before __future__ — reorder
        lines.pop(pdmsg_idx)
        src = "".join(lines)
        insert = 0
        if lines and lines[0].startswith("#!"):
            insert = 1
        if insert < len(lines) and lines[insert].startswith('"""'):
            if lines[insert].count('"""') >= 2:
                insert += 1
            else:
                insert += 1
                while insert < len(lines) and '"""' not in lines[insert]:
                    insert += 1
                insert += 1
        while insert < len(lines) and (
            lines[insert].startswith("from __future__") or lines[insert].strip() == ""
        ):
            if lines[insert].startswith("from __future__"):
                insert += 1
            elif lines[insert].strip() == "":
                insert += 1
            else:
                break
        lines.insert(insert, PDMSG)
        src = "".join(lines)
    if src != orig:
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main() -> None:
    n = 0
    for p in ROOT.rglob("*.py"):
        if "venv" in p.parts:
            continue
        if fix(p):
            n += 1
            print("fixed", p.relative_to(ROOT))
    print(f"done: {n}")


if __name__ == "__main__":
    main()
