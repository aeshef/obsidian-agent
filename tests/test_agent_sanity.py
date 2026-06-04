"""Agent tool registry shape for capability presets (no Telegram)."""
from __future__ import annotations

from shared.capabilities.onboarding_verify import agent_registry_sanity
from shared.capabilities.presets import PRESET_PLANNING_ONLY, preset_document


def test_planning_only_registry():
    errs = agent_registry_sanity(preset_document(PRESET_PLANNING_ONLY))
    assert errs == [], errs
