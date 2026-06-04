"""Prompt capability blocks."""
from __future__ import annotations

from shared.capabilities.profile import (
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    MODULE_PLANNING,
    CapabilityProfile,
)
from shared.capabilities.prompt_filter import filter_prompt_capabilities


def test_cap_block_removed_when_connector_off():
    text = "A\n<!-- @cap broker -->\nB\n<!-- @/cap -->\nC"
    prof = CapabilityProfile(
        modules={"finance": True, "planning": True, "knowledge": False},
        connectors={CONNECTOR_BROKER_SYNC: False},
        sync_profile="full",
    )
    out = filter_prompt_capabilities(text, prof)
    assert "A" in out and "C" in out
    assert "B" not in out


def test_cap_block_kept_when_connector_on():
    text = "<!-- @cap health -->\nmetrics\n<!-- @/cap -->"
    prof = CapabilityProfile(
        modules={"finance": False, "planning": True, "knowledge": False},
        connectors={CONNECTOR_APPLE_HEALTH: True},
        sync_profile="full",
    )
    assert "metrics" in filter_prompt_capabilities(text, prof)


def test_module_cap():
    text = "<!-- @cap planning -->\nkanban\n<!-- @/cap -->"
    prof = CapabilityProfile(
        modules={"finance": False, "planning": False, "knowledge": False},
        connectors={},
        sync_profile="planning_kanban",
    )
    assert "kanban" not in filter_prompt_capabilities(text, prof)
