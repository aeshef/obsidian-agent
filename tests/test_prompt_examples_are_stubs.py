"""User-facing strings live in YAML configs."""
from __future__ import annotations

import subprocess
from pathlib import Path

from shared.prompts import _is_comment_stub

ROOT = Path(__file__).resolve().parents[1]


def test_all_tracked_prompt_examples_are_comment_stubs():
    out = subprocess.check_output(
        ["git", "ls-files", "**/*.example.txt"],
        cwd=ROOT,
        text=True,
    ).strip()
    paths = [p for p in out.splitlines() if p]
    assert paths, "no *.example.txt in git index"
    bad = []
    for rel in paths:
        text = (ROOT / rel).read_text(encoding="utf-8").strip()
        if not _is_comment_stub(text):
            bad.append(rel)
    assert not bad, f"example files must be comment-only stubs: {bad}"
