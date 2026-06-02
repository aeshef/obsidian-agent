"""Fail if any tracked Python source contains Cyrillic (UI belongs in YAML)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CYR_RANGE = f"[{chr(0x400)}-{chr(0x4FF)}]"
CYRILLIC = re.compile(_CYR_RANGE)
UNICODE_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")
SKIP_DIR_NAMES = {
    "venv",
    ".venv",
    ".venv-scrub",
    "__pycache__",
    ".git",
    "migration",
    "tests",
    "site-packages",
}
SKIP_PATH_PARTS = ("knowledge_bot/tools", "planning_bot/scripts")
SKIP_FILE_PREFIXES = (".scrub_",)


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in rel for part in SKIP_PATH_PARTS):
            continue
        if rel.startswith("scripts/"):
            continue
        if path.name.startswith(SKIP_FILE_PREFIXES):
            continue
        out.append(path)
    return sorted(out)


def test_no_cyrillic_in_python_sources() -> None:
    offenders: list[str] = []
    for path in _iter_py_files():
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CYRILLIC.search(line):
                offenders.append(f"{rel}:{lineno}: cyrillic: {line.strip()[:120]}")
            elif UNICODE_ESCAPE.search(line):
                offenders.append(f"{rel}:{lineno}: unicode_escape: {line.strip()[:120]}")
    assert not offenders, "Cyrillic/\\u escapes in .py (use kmsg/dmsg + YAML):\n" + "\n".join(offenders[:80])


def test_no_cyrillic_count_is_zero() -> None:
    total = sum(
        1
        for path in _iter_py_files()
        for line in path.read_text(encoding="utf-8").splitlines()
        if CYRILLIC.search(line)
    )
    assert total == 0, f"{total} lines still contain Cyrillic"
