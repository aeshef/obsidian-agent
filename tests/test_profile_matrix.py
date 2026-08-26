"""Preset profiles must keep modules/connectors/sync consistent."""
from __future__ import annotations

from shared.capabilities.presets import (
    PRESET_FINANCE_ONLY,
    PRESET_MINIMAL,
    PRESET_PLANNING_ONLY,
    preset_document,
)
from shared.capabilities.profile import (
    CONNECTOR_BROKER_SYNC,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    profile_from_document,
)
from shared.capabilities.sync_steps import STEP_FINANCE_DASHBOARD, sync_step_enabled


def test_planning_only_preset():
    prof = profile_from_document(preset_document(PRESET_PLANNING_ONLY))
    assert prof.module(MODULE_PLANNING)
    assert not prof.module(MODULE_FINANCE)
    assert not prof.module(MODULE_KNOWLEDGE)
    assert not prof.connector(CONNECTOR_BROKER_SYNC)
    assert not sync_step_enabled(STEP_FINANCE_DASHBOARD, prof)


def test_finance_only_preset():
    prof = profile_from_document(preset_document(PRESET_FINANCE_ONLY))
    assert prof.module(MODULE_FINANCE)
    assert not prof.module(MODULE_PLANNING)
    assert sync_step_enabled(STEP_FINANCE_DASHBOARD, prof)


def test_minimal_preset():
    prof = profile_from_document(preset_document(PRESET_MINIMAL))
    assert prof.module(MODULE_FINANCE)
    assert not prof.module(MODULE_PLANNING)


def test_knowledge_only_preset():
    from shared.capabilities.presets import PRESET_KNOWLEDGE_ONLY
    from shared.capabilities.sync_steps import STEP_KB_MAINTENANCE

    prof = profile_from_document(preset_document(PRESET_KNOWLEDGE_ONLY))
    assert prof.module(MODULE_KNOWLEDGE)
    assert not prof.module(MODULE_FINANCE)
    assert not prof.module(MODULE_PLANNING)
    assert sync_step_enabled(STEP_KB_MAINTENANCE, prof)
    assert not sync_step_enabled(STEP_FINANCE_DASHBOARD, prof)
