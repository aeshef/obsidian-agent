"""Capabilities manifest: defaults preserve full product; profiles gate sync/tools."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from shared.capabilities.profile import (
    CONNECTOR_BROKER_SYNC,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    SYNC_PROFILE_FINANCE_ONLY,
    SYNC_PROFILE_FULL,
    CapabilityProfile,
    clear_capabilities_cache,
    load_capabilities,
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
    # Example template must not act as live config when capabilities.yaml is absent.
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


def test_finance_only_profile_disables_planning_sync(tmp_path: Path):
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
    os.environ["CAPABILITIES_PATH"] = str(cfg)
    clear_capabilities_cache()
    prof = load_capabilities()
    assert not prof.module(MODULE_PLANNING)
    assert sync_step_enabled(STEP_FINANCE_DASHBOARD, prof)
    assert not sync_step_enabled(STEP_PLANNING_CHARTS, prof)
    assert not sync_step_enabled(STEP_KB_MAINTENANCE, prof)


def test_connector_off_filters_finance_broker_tool():
    prof = CapabilityProfile(
        modules={MODULE_FINANCE: True, MODULE_PLANNING: True, MODULE_KNOWLEDGE: True},
        connectors={CONNECTOR_BROKER_SYNC: False},
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
    os.environ["CAPABILITIES_PATH"] = str(cfg)
    clear_capabilities_cache()
    from shared.capabilities.sync_steps import export_shell_env

    env = export_shell_env()
    assert "CAP_MODULE_FINANCE=1" in env
    assert "CAP_MODULE_PLANNING=0" in env
    assert "CAP_SYNC_PLANNING_CHARTS=0" in env


def test_broker_exact_command_filtered(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    clear_capabilities_cache()
    from shared.capabilities.finance_gates import filter_finance_exact_commands

    cmds = filter_finance_exact_commands({"Синк Тинькофф", "Баланс"})
    assert "Синк Тинькофф" not in cmds
    assert "Баланс" in cmds
    monkeypatch.delenv("CAP_CONNECTOR_BROKER_SYNC", raising=False)
    clear_capabilities_cache()
