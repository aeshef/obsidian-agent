"""Ban call-site temperature=0.x literals outside tests (OSS audit F14)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PAT = re.compile(r"temperature\s*=\s*0\.\d+")
_SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "tests", "eval"}


def test_no_temperature_literals_in_product_code():
    bad: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(p in _SKIP_DIRS for p in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _PAT.search(line):
                bad.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not bad, "temperature literals must live in YAML:\n" + "\n".join(bad)
