#!/usr/bin/env python3
"""
Fix \\uXXXX artifacts in .py sources:
1) restore from git HEAD when HEAD has no escapes
2) else rewrite string literals to UTF-8 JSON form (readable Cyrillic, not \\u escapes)
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tokenize
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESC = re.compile(r"\\u[0-9a-fA-F]{4}")
SKIP_DIRS = {"venv", ".venv", ".venv-scrub", "__pycache__", ".git", "migration"}
SKIP_PREFIX = (".scrub_",)
SKIP_FILES = {
    "scripts/fix_all_unicode_escapes.py",
    "scripts/normalize_string_literals.py",
    "scripts/repair_unicode_escapes.py",
    "tests/test_no_cyrillic_in_py.py",
}


def _offset(source: str, start: tuple[int, int], end: tuple[int, int]) -> tuple[int, int]:
    lines = source.splitlines(keepends=True)
    s = sum(len(lines[i]) for i in range(start[0] - 1))
    e = sum(len(lines[i]) for i in range(end[0] - 1))
    return s + start[1], e + end[1]


def _normalize_literals(source: str) -> str:
    tokens = list(tokenize.generate_tokens(StringIO(source).readline))
    out: list[str] = []
    pos = 0
    for tok in tokens:
        if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        start, end = _offset(source, tok.start, tok.end)
        out.append(source[pos:start])
        chunk = source[start:end]
        if tok.type == tokenize.STRING and ESC.search(chunk):
            try:
                val = ast.literal_eval(chunk)
                if isinstance(val, str):
                    chunk = json.dumps(val, ensure_ascii=False)
            except (ValueError, SyntaxError):
                pass
        out.append(chunk)
        pos = end
    out.append(source[pos:])
    return "".join(out)


def _git_head_text(rel: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    return r.stdout


def _should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in SKIP_FILES:
        return True
    if any(p in SKIP_DIRS for p in path.parts):
        return True
    if path.name.startswith(SKIP_PREFIX):
        return True
    if "planning_bot/scripts/migrate_cyrillic" in rel or rel.endswith("zero_cyrillic.py"):
        return True
    if "planning_bot/scripts/patch_scripts" in rel:
        return True
    return False


def fix_file(path: Path, *, dry_run: bool) -> str:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    if not ESC.search(text):
        return "skip"

    head = _git_head_text(rel)
    if head is not None and not ESC.search(head):
        if not dry_run:
            path.write_text(head, encoding="utf-8")
        return "restored"

    new = _normalize_literals(text)
    if new != text:
        if not dry_run:
            path.write_text(new, encoding="utf-8")
        return "normalized"
    return "unchanged"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats: dict[str, int] = {}
    for path in sorted(ROOT.rglob("*.py")):
        if _should_skip(path):
            continue
        action = fix_file(path, dry_run=args.dry_run)
        stats[action] = stats.get(action, 0) + 1
        if action not in ("skip", "unchanged"):
            print(f"{action}: {path.relative_to(ROOT)}")
    print("stats", stats, file=sys.stderr)
    remaining = 0
    for path in ROOT.rglob("*.py"):
        if _should_skip(path):
            continue
        if ESC.search(path.read_text(encoding="utf-8")):
            remaining += 1
            print(f"still has escapes: {path.relative_to(ROOT)}", file=sys.stderr)
    return 1 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
