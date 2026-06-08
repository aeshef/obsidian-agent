#!/usr/bin/env python3
"""Fill planning_bot/config/prompts/*.txt from *.example.txt when only comment-stub exists."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "planning_bot" / "config" / "prompts"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from shared.prompts import _is_comment_stub

    written = 0
    for example in sorted(PROMPTS.glob("*.example.txt")):
        name = example.name.replace(".example.txt", "")
        path = PROMPTS / f"{name}.txt"
        if path.is_file():
            cur = path.read_text(encoding="utf-8").strip()
            if cur and not _is_comment_stub(cur):
                continue
        text = example.read_text(encoding="utf-8").strip()
        if not text or _is_comment_stub(text):
            continue
        path.write_text(text + "\n", encoding="utf-8")
        print(f"seeded: {path.relative_to(ROOT)}")
        written += 1
    print(f"seed_planning_prompts: {written} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
