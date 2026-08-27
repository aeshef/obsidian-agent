"""Fact coverage scorer for gold baskets."""
from __future__ import annotations

from shared.agent.fact_coverage import score_facts


def test_score_facts_full_hit():
    got = score_facts("Unique: 5 — Ship docs", expected_facts=["5", "Ship docs"])
    assert got["coverage"] == 1.0
    assert not got["miss"]


def test_score_facts_forbidden():
    got = score_facts("закрыл 4 задач", expected_facts=["17"], forbidden_facts=["4 задач"])
    assert got["coverage"] == 0.0
    assert got["forbidden_hit"] == ["4 задач"]
