"""Prompt files: git has only comment-stub *.example.txt; prod *.txt is gitignored."""
from __future__ import annotations

import subprocess
from pathlib import Path

from shared.prompts import _is_comment_stub

ROOT = Path(__file__).resolve().parents[1]

PROMPT_GLOB_PATTERNS = (
    "**/config/prompts/*.txt",
    "config/agent/prompts/*.txt",
)


def _git_ls_files(*patterns: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files", *patterns],
        cwd=ROOT,
        text=True,
    ).strip()
    return [p for p in out.splitlines() if p]


def test_no_tracked_prod_prompt_txt_in_git():
    tracked = _git_ls_files(*PROMPT_GLOB_PATTERNS)
    prod = [p for p in tracked if p.endswith(".txt") and not p.endswith(".example.txt")]
    assert not prod, f"prod prompt .txt must not be in git index: {prod}"


def test_all_tracked_prompt_examples_are_comment_stubs():
    tracked = _git_ls_files("**/*.example.txt")
    prompt_examples = [
        p for p in tracked if "/prompts/" in p or p.startswith("config/agent/prompts/")
    ]
    assert prompt_examples, "no prompt *.example.txt in git index"
    bad = []
    for rel in prompt_examples:
        text = (ROOT / rel).read_text(encoding="utf-8").strip()
        if not _is_comment_stub(text):
            bad.append(rel)
    assert not bad, f"prompt example files must be comment-only stubs: {bad}"


def test_every_tracked_prompt_example_has_local_or_git_path():
    """Each *.example.txt in index must exist on disk (CI checkout)."""
    for rel in _git_ls_files("**/config/prompts/*.example.txt", "config/agent/prompts/*.example.txt"):
        assert (ROOT / rel).is_file(), rel
