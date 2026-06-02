#!/usr/bin/env python3
"""
AUDIT ONLY — lists \\uXXXX escapes and suggests YAML keys.
Do not auto-edit files (token replace can corrupt source). Use audit_refactor_artifacts.py.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
import tokenize
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")
SKIP_DIRS = {"venv", ".venv", ".venv-scrub", "__pycache__", ".git", "migration"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("roots", nargs="*", default=["."])
    args = ap.parse_args()
    count = 0
    for root_name in args.roots:
        root = ROOT / root_name if root_name != "." else ROOT
        for path in root.rglob("*.py"):
            if any(p in SKIP_DIRS for p in path.parts) or path.name.startswith(".scrub_"):
                continue
            text = path.read_text(encoding="utf-8")
            if not ESCAPE.search(text):
                continue
            for tok in tokenize.generate_tokens(StringIO(text).readline):
                if tok.type != tokenize.STRING or not ESCAPE.search(tok.string):
                    continue
                try:
                    val = ast.literal_eval(tok.string)
                except (ValueError, SyntaxError):
                    val = tok.string[:60]
                rel = path.relative_to(ROOT)
                print(f"{rel}:{tok.start[0]}: {val!r:.80}")
                count += 1
    print("total", count, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
