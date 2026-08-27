"""Deterministic fact coverage for gold baskets (no LLM-judge)."""
from __future__ import annotations

from typing import Any


def norm_text(s: str) -> str:
    return " ".join((s or "").casefold().split())


def score_facts(
    answer: str,
    *,
    expected_facts: list[str] | None = None,
    forbidden_facts: list[str] | None = None,
) -> dict[str, Any]:
    """Return coverage = hit/expected; forbidden_hit list when present in answer."""
    body = norm_text(answer)
    expected = [str(x) for x in (expected_facts or []) if str(x).strip()]
    forbidden = [str(x) for x in (forbidden_facts or []) if str(x).strip()]
    hit = [f for f in expected if norm_text(f) in body]
    miss = [f for f in expected if norm_text(f) not in body]
    bad_hit = [f for f in forbidden if norm_text(f) in body]
    cov = (len(hit) / len(expected)) if expected else None
    return {
        "coverage": cov,
        "hit": hit,
        "miss": miss,
        "forbidden_hit": bad_hit,
        "expected_n": len(expected),
        "forbidden_n": len(forbidden),
    }
