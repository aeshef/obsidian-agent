"""Personalized prompts must have English scaffolds for first-run materialization."""
from __future__ import annotations

from pathlib import Path

from shared.capabilities.prompt_manifest import personalized_prompts
from shared.capabilities.prompt_scaffold_templates import SCAFFOLDS, load_scaffold_body

ROOT = Path(__file__).resolve().parents[1]


def test_all_personalized_have_scaffolds() -> None:
    missing = [
        p
        for p in personalized_prompts()
        if not (ROOT / p).is_file() and p not in SCAFFOLDS
    ]
    assert not missing, (
        "Add *.example.txt or prompt_scaffold_templates.SCAFFOLDS:\n" + "\n".join(missing)
    )
