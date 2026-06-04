"""Personalized prompts must have English scaffolds for first-run materialization."""
from __future__ import annotations

from shared.capabilities.prompt_manifest import personalized_prompts
from shared.capabilities.prompt_scaffold_templates import SCAFFOLDS


def test_all_personalized_have_scaffolds() -> None:
    missing = [p for p in personalized_prompts() if p not in SCAFFOLDS]
    assert not missing, "Add to prompt_scaffold_templates.SCAFFOLDS:\n" + "\n".join(missing)
