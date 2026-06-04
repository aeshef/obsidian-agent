"""Prompt example policy: generic_en in git vs personalized stubs."""
from __future__ import annotations

from pathlib import Path

from shared.capabilities.prompt_manifest import (
    generic_en_prompts,
    list_tracked_example_prompts,
    personalized_prompts,
    prompt_tier,
)
from shared.prompts import _is_comment_stub

ROOT = Path(__file__).resolve().parents[1]


def test_tracked_prompt_examples_tier_policy():
    paths = list_tracked_example_prompts()
    assert paths, "no *.example.txt in git index"
    bad: list[str] = []
    for rel in paths:
        text = (ROOT / rel).read_text(encoding="utf-8").strip()
        tier = prompt_tier(rel)
        is_stub = _is_comment_stub(text)
        if tier == "generic_en":
            if is_stub or len(text) < 40:
                bad.append(f"{rel}: generic_en must contain working English prompt text")
        else:
            if not is_stub:
                bad.append(f"{rel}: {tier} must be comment-only stub in git")
    assert not bad, "\n".join(bad)


def test_manifest_covers_agent_routers():
    for name in (
        "config/agent/prompts/host_domain_router.example.txt",
        "config/agent/prompts/finance_intent_router.example.txt",
    ):
        assert name in generic_en_prompts()


def test_personalized_includes_nlu():
    assert "finance_bot/config/prompts/nlu_prompt.example.txt" in personalized_prompts()
