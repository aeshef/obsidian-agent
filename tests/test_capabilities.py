"""Capabilities manifest: full-install / starter defaults; partial YAML is fail-closed."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from shared.capabilities.profile import (
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_APPLE_HEALTH,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    SYNC_PROFILE_FINANCE_ONLY,
    SYNC_PROFILE_FULL,
    CapabilityProfile,
    clear_capabilities_cache,
    load_capabilities,
    profile_from_document,
)
from shared.capabilities.registry import filter_finance_tools, filter_planning_tools
from shared.capabilities.sync_steps import (
    STEP_FINANCE_DASHBOARD,
    STEP_GMAIL_HEALTH,
    STEP_KB_MAINTENANCE,
    STEP_PLANNING_CHARTS,
    sync_step_enabled,
)


@pytest.fixture(autouse=True)
def _clear_cap_cache(monkeypatch):
    monkeypatch.delenv("CAPABILITIES_PATH", raising=False)
    monkeypatch.delenv("CAPABILITIES_SYNC_PROFILE", raising=False)
    for key in list(os.environ):
        if key.startswith("CAP_MODULE_") or key.startswith("CAP_CONNECTOR_"):
            monkeypatch.delenv(key, raising=False)
    clear_capabilities_cache()
    yield
    clear_capabilities_cache()


def test_missing_manifest_defaults_full_product(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSIDIAN_AGENT_FULL_INSTALL", "1")
    monkeypatch.setenv("CAPABILITIES_PATH", str(tmp_path / "nonexistent.yaml"))
    clear_capabilities_cache()
    prof = load_capabilities()
    assert prof.module(MODULE_FINANCE)
    assert prof.module(MODULE_PLANNING)
    assert prof.module(MODULE_KNOWLEDGE)
    assert prof.connector(CONNECTOR_BROKER_SYNC)
    assert prof.sync_profile == SYNC_PROFILE_FULL
    assert sync_step_enabled(STEP_PLANNING_CHARTS, prof)
    assert sync_step_enabled(STEP_GMAIL_HEALTH, prof)
    assert sync_step_enabled(STEP_KB_MAINTENANCE, prof)
    assert sync_step_enabled(STEP_FINANCE_DASHBOARD, prof)


def test_missing_manifest_uses_oss_starter(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("OBSIDIAN_AGENT_FULL_INSTALL", raising=False)
    monkeypatch.setenv("CAPABILITIES_PATH", str(tmp_path / "nonexistent.yaml"))
    clear_capabilities_cache()
    prof = load_capabilities()
    assert prof.module(MODULE_FINANCE)
    assert prof.module(MODULE_PLANNING)
    assert not prof.module(MODULE_KNOWLEDGE)
    assert not prof.connector(CONNECTOR_BROKER_SYNC)
    assert prof.sync_profile == "planning_light"


def test_finance_only_profile_disables_planning_sync(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "capabilities.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "modules": {"finance": True, "planning": False, "knowledge": False},
                "connectors": {"domestic_bank_cards": True},
                "sync": {"profile": SYNC_PROFILE_FINANCE_ONLY},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAPABILITIES_PATH", str(cfg))
    clear_capabilities_cache()
    prof = load_capabilities()
    assert not prof.module(MODULE_PLANNING)
    assert sync_step_enabled(STEP_FINANCE_DASHBOARD, prof)
    assert not sync_step_enabled(STEP_PLANNING_CHARTS, prof)
    assert not sync_step_enabled(STEP_KB_MAINTENANCE, prof)
    # Fail-closed: omitted connectors stay off.
    assert not prof.connector(CONNECTOR_BROKER_SYNC)


def test_partial_yaml_omitted_keys_fail_closed():
    prof = profile_from_document(
        {"modules": {"finance": True}, "sync": {"profile": SYNC_PROFILE_FINANCE_ONLY}}
    )
    assert prof.module(MODULE_FINANCE)
    assert not prof.module(MODULE_PLANNING)
    assert not prof.module(MODULE_KNOWLEDGE)
    assert not prof.connector(CONNECTOR_BROKER_SYNC)
    assert not prof.connector(CONNECTOR_APPLE_HEALTH)


def test_connector_off_filters_finance_broker_tool():
    from shared.capabilities.profile import CONNECTOR_MANUAL_BROKER

    prof = CapabilityProfile(
        modules={MODULE_FINANCE: True, MODULE_PLANNING: True, MODULE_KNOWLEDGE: True},
        connectors={CONNECTOR_BROKER_SYNC: False, CONNECTOR_MANUAL_BROKER: False},
        sync_profile=SYNC_PROFILE_FULL,
    )

    class _Tool:
        def __init__(self, name: str):
            self.__name__ = name

    tools = [
        _Tool("get_balance"),
        _Tool("get_broker_overview"),
    ]
    filtered = filter_finance_tools(tools, prof)
    names = [t.__name__ for t in filtered]
    assert "get_balance" in names
    assert "get_broker_overview" not in names


def test_planning_health_tools_need_apple_health_connector():
    from shared.capabilities.profile import CONNECTOR_APPLE_HEALTH

    prof = CapabilityProfile(
        modules={MODULE_FINANCE: False, MODULE_PLANNING: True, MODULE_KNOWLEDGE: False},
        connectors={CONNECTOR_APPLE_HEALTH: False},
        sync_profile=SYNC_PROFILE_FULL,
    )

    class _Tool:
        def __init__(self, name: str):
            self.__name__ = name

    tools = [_Tool("get_health_snapshot"), _Tool("list_tasks")]
    filtered = filter_planning_tools(tools, prof)
    names = [t.__name__ for t in filtered]
    assert "list_tasks" in names
    assert "get_health_snapshot" not in names


def test_is_badge_enabled_respects_connector(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_CORPORATE_BADGE", "0")
    clear_capabilities_cache()
    from bot.config_loader import _config_cache, is_badge_enabled

    _config_cache["badge"] = {"enabled": True}
    try:
        assert is_badge_enabled() is False
    finally:
        _config_cache.pop("badge", None)
        monkeypatch.delenv("CAP_CONNECTOR_CORPORATE_BADGE", raising=False)
        clear_capabilities_cache()


def test_export_shell_env_includes_modules(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "capabilities.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "modules": {"finance": True, "planning": False, "knowledge": False},
                "sync": {"profile": SYNC_PROFILE_FINANCE_ONLY},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAPABILITIES_PATH", str(cfg))
    clear_capabilities_cache()
    from shared.capabilities.sync_steps import export_shell_env

    env = export_shell_env()
    assert "CAP_MODULE_FINANCE=1" in env
    assert "CAP_MODULE_PLANNING=0" in env
    assert "CAP_SYNC_PLANNING_CHARTS=0" in env


def test_feature_off_disables_nutrition_sync(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "capabilities.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "modules": {"finance": False, "planning": True, "knowledge": False},
                "connectors": {
                    "apple_health": True,
                    "apple_calendar": True,
                    "mac_context": True,
                },
                "features": {"health_nutrition_chart": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAPABILITIES_PATH", str(cfg))
    clear_capabilities_cache()
    from shared.capabilities.sync_steps import STEP_NUTRITION, sync_step_enabled

    prof = load_capabilities()
    assert not sync_step_enabled(STEP_NUTRITION, prof)


def test_planning_weekly_review_feature_off(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "capabilities.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "modules": {"planning": True},
                "features": {"planning_weekly_review": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAPABILITIES_PATH", str(cfg))
    clear_capabilities_cache()
    from shared.capabilities.planning_gates import planning_weekly_review_enabled

    assert not planning_weekly_review_enabled()


def test_infer_planning_only_sync_profile():
    from shared.capabilities.compose import infer_sync_profile

    doc = {
        "modules": {"finance": False, "planning": True, "knowledge": False},
        "connectors": {c: False for c in (
            "corporate_badge", "broker_sync", "manual_broker_accounts",
            "apple_health", "gmail_health_pipeline", "apple_calendar",
            "mac_context", "knowledge_serendipity",
        )},
    }
    from shared.capabilities.profile import SYNC_PROFILE_PLANNING_KANBAN

    assert infer_sync_profile(doc) == SYNC_PROFILE_PLANNING_KANBAN


def test_manual_broker_tool_without_api_connector():
    from shared.capabilities.profile import CONNECTOR_BROKER_SYNC, CONNECTOR_MANUAL_BROKER

    prof = CapabilityProfile(
        modules={"finance": True, "planning": False, "knowledge": False},
        connectors={CONNECTOR_BROKER_SYNC: False, CONNECTOR_MANUAL_BROKER: True},
        sync_profile="finance_only",
    )

    class _Tool:
        def __init__(self, name: str):
            self.__name__ = name

    filtered = filter_finance_tools([_Tool("get_broker_overview")], prof)
    assert len(filtered) == 1


def test_broker_exact_command_filtered(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    clear_capabilities_cache()
    from shared.capabilities.finance_gates import filter_finance_exact_commands
    from shared.i18n import msg_raw

    broker_cmd = msg_raw("finance", "exact_command_broker_sync") or msg_raw(
        "finance", "exact_command_tinkoff_sync"
    )
    assert broker_cmd
    cmds = filter_finance_exact_commands({broker_cmd, "Баланс"})
    assert broker_cmd not in cmds
    assert "Баланс" in cmds
    monkeypatch.delenv("CAP_CONNECTOR_BROKER_SYNC", raising=False)
    clear_capabilities_cache()
