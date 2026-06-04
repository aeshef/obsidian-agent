#!/usr/bin/env python3
"""Audit refactor artifacts: syntax, unicode escapes, hardcoded paths, UI literals."""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"venv", ".venv", ".venv-scrub", "__pycache__", ".git", "migration"}
SKIP_FILE_PREFIX = (".scrub_",)

_CYR = f"[{chr(0x400)}-{chr(0x4FF)}]"
CYRILLIC = re.compile(_CYR)
UNICODE_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")
VAULT_PATH_LITERAL = re.compile(
    rf'["\'](?:100_|200_|300_|400_|600_|700_|800_)[^"\']*["\']'
    rf'|["\']{_CYR}[^"\']*["\']'
)
BROKEN_FOLDER = re.compile(r'folder\s*/\s*["\']|folder/Users')
INLINE_BTN = re.compile(r'InlineKeyboardButton\s*\(\s*text\s*=\s*["\']')
PROMPT_TXT = re.compile(r'config/prompts/[^"\']+\.txt|_load_prompt\s*\(\s*["\']')
BROKEN_MSG_FN = re.compile(r"\b[rk]pdmsg\s*\(")


def iter_py() -> list[Path]:
    out: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if any(p in SKIP_DIRS for p in path.parts):
            continue
        if path.name.startswith(SKIP_FILE_PREFIX):
            continue
        out.append(path)
    return sorted(out)


def check_syntax(path: Path) -> str | None:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        return f"{path.relative_to(ROOT)}:{e.lineno}: {e.msg}"
    return None


def scan_file(path: Path) -> dict[str, list[str]]:
    rel = str(path.relative_to(ROOT))
    text = path.read_text(encoding="utf-8")
    issues: dict[str, list[str]] = {}
    for i, line in enumerate(text.splitlines(), 1):
        if UNICODE_ESCAPE.search(line):
            issues.setdefault("unicode_escape", []).append(f"{rel}:{i}")
        if CYRILLIC.search(line):
            issues.setdefault("cyrillic", []).append(f"{rel}:{i}")
        if VAULT_PATH_LITERAL.search(line) and "vault_paths" not in line and "yaml.example" not in line:
            issues.setdefault("vault_path_literal", []).append(f"{rel}:{i}: {line.strip()[:100]}")
        if BROKEN_FOLDER.search(line):
            issues.setdefault("broken_folder", []).append(f"{rel}:{i}: {line.strip()[:100]}")
        if INLINE_BTN.search(line) and "fmsg(" not in line and "kmsg(" not in line and "pmsg(" not in line and "common(" not in line and "msg(" not in line:
            issues.setdefault("inline_button_literal", []).append(f"{rel}:{i}")
        if PROMPT_TXT.search(line) and ".example" not in line:
            issues.setdefault("prompt_path", []).append(f"{rel}:{i}")
        if BROKEN_MSG_FN.search(line):
            issues.setdefault("broken_msg_fn", []).append(f"{rel}:{i}: {line.strip()[:100]}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable counts only")
    args = parser.parse_args()

    syntax_errors: list[str] = []
    merged: dict[str, list[str]] = {}
    for path in iter_py():
        err = check_syntax(path)
        if err:
            syntax_errors.append(err)
        for kind, items in scan_file(path).items():
            merged.setdefault(kind, []).extend(items)

    if args.json:
        print({k: len(v) for k, v in merged.items()}, "syntax", len(syntax_errors))
        return 1 if syntax_errors or merged else 0

    print("=== Syntax errors ===")
    if syntax_errors:
        for e in syntax_errors:
            print(e)
    else:
        print("(none)")

    for kind in (
        "unicode_escape",
        "cyrillic",
        "vault_path_literal",
        "broken_folder",
        "inline_button_literal",
        "prompt_path",
    ):
        items = merged.get(kind, [])
        print(f"\n=== {kind} ({len(items)}) ===")
        for line in items[:40]:
            print(line)
        if len(items) > 40:
            print(f"... +{len(items) - 40} more")

    return 1 if syntax_errors else 0


if __name__ == "__main__":
    sys.exit(main())
