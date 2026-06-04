#!/usr/bin/env python3
"""Promote stray `    auto_xxx:` lines inside block scalars to top-level planning keys."""
from __future__ import annotations

import re
import sys
from pathlib import Path

STRAY_KEY = re.compile(r"^    (auto_[a-f0-9]+: .*)$")


def fix_text(text: str) -> tuple[str, int]:
    fixed = 0
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        m = STRAY_KEY.match(line.rstrip("\n"))
        if m:
            out.append("  " + m.group(1) + ("\n" if line.endswith("\n") else ""))
            fixed += 1
        else:
            out.append(line)
    return "".join(out), fixed


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    total = 0
    for name in ("domain_messages.yaml", "domain_messages.yaml.example"):
        path = root / "config" / name
        if not path.is_file():
            continue
        new, n = fix_text(path.read_text(encoding="utf-8"))
        if n:
            path.write_text(new, encoding="utf-8")
            print(f"{name}: promoted {n} stray keys")
            total += n
        else:
            print(f"{name}: ok")
    return 0 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
