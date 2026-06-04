#!/usr/bin/env python3
"""Normalize indentation for `  key: |` block scalars in domain_messages YAML."""
from __future__ import annotations

import re
import sys
from pathlib import Path

KEY_LINE = re.compile(r"^  [a-z0-9_]+: (.*)$")
BLOCK_KEY = re.compile(r"^  [a-z0-9_]+: \|$")


def fix_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if BLOCK_KEY.match(line.rstrip("\n")):
            out.append(line)
            i += 1
            block_lines: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                bare = nxt.rstrip("\n")
                if KEY_LINE.match(bare) and not bare.endswith("|"):
                    break
                block_lines.append(nxt)
                i += 1
            # Normalize: content indent = 4 spaces (deeper than 2-space keys)
            norm: list[str] = []
            for bl in block_lines:
                if bl.strip() == "":
                    norm.append("\n")
                    continue
                stripped = bl.lstrip(" ")
                norm.append("    " + stripped + ("\n" if bl.endswith("\n") else ""))
            out.extend(norm)
            continue
        out.append(line)
        i += 1
    return out


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    for name in ("domain_messages.yaml", "domain_messages.yaml.example"):
        path = root / "config" / name
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        fixed = fix_lines(lines)
        text = "".join(fixed)
        if text != "".join(lines):
            path.write_text(text, encoding="utf-8")
            print(f"fixed {name}")
        else:
            print(f"unchanged {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
