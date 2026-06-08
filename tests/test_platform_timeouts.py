"""platform.yaml timeout sections are wired for prod callers."""
from __future__ import annotations

from pathlib import Path

from shared.platform_timeouts import (
    asr_http_timeout_sec,
    knowledge_text_intent_timeout_sec,
    llm_reachable_timeout_sec,
)
from shared.yaml_config import load_yaml


def test_platform_example_has_timeout_sections():
    raw = load_yaml(
        Path(__file__).resolve().parent.parent / "config/agent/platform.yaml.example",
        default={},
    )
    assert raw["asr"]["http_timeout_sec"] == 600
    assert raw["knowledge_extract"]["text_intent_timeout_sec"] == 45
    assert raw["planning_llm"]["routines_recommendations"] == 0.7


def test_platform_timeout_helpers_return_positive():
    assert asr_http_timeout_sec() > 0
    assert knowledge_text_intent_timeout_sec() > 0
    assert llm_reachable_timeout_sec() > 0
