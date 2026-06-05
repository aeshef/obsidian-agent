"""LLM defaults from config/agent/models.yaml."""
from __future__ import annotations

from shared.llm_defaults import role_temperature, role_timeout_sec


def test_role_temperature_analyze_default():
    t = role_temperature("analyze")
    assert 0.0 < t < 1.0


def test_role_timeout_analyze_default():
    sec = role_timeout_sec("analyze")
    assert sec >= 30.0
