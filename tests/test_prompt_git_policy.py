"""Prompt files: git has only comment-stub *.example.txt; prod *.txt is gitignored."""
from __future__ import annotations

import subprocess
from pathlib import Path

from shared.capabilities.prompt_manifest import list_tracked_example_prompts, prompt_tier
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


def test_personalized_prompt_examples_are_comment_stubs():
    """generic_en examples ship working English text; personalized_* stay comment stubs."""
    paths = list_tracked_example_prompts()
    assert paths, "no prompt *.example.txt in git index"
    bad = []
    for rel in paths:
        if prompt_tier(rel) == "generic_en":
            continue
        text = (ROOT / rel).read_text(encoding="utf-8").strip()
        if not _is_comment_stub(text):
            bad.append(rel)
    assert not bad, f"personalized prompt examples must be comment-only stubs: {bad}"


def test_every_tracked_prompt_example_has_local_or_git_path():
    """Each *.example.txt in index must exist on disk (CI checkout)."""
    for rel in _git_ls_files("**/config/prompts/*.example.txt", "config/agent/prompts/*.example.txt"):
        assert (ROOT / rel).is_file(), rel
