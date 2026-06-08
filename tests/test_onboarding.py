"""Presets, builder, vault layout planning."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from shared.capabilities.builder import build_capabilities_document
from shared.capabilities.presets import PRESET_FINANCE_ONLY, preset_document
from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_BROKER_SYNC,
    clear_capabilities_cache,
    load_capabilities,
)
from shared.capabilities.vault_init import planned_vault_dirs


@pytest.fixture(autouse=True)
def _clear_cap(monkeypatch):
    monkeypatch.delenv("CAPABILITIES_PATH", raising=False)
    clear_capabilities_cache()
    yield
    clear_capabilities_cache()


def test_finance_only_preset():
    doc = preset_document(PRESET_FINANCE_ONLY)
    assert doc["modules"][MODULE_FINANCE] is True
    assert doc["modules"][MODULE_PLANNING] is False
    assert doc["connectors"][CONNECTOR_BROKER_SYNC] is False


def test_only_modules_planning():
    doc = build_capabilities_document(only_modules=["planning"])
    assert doc["modules"]["planning"] is True
    assert doc["modules"]["finance"] is False
    assert doc["sync"]["profile"] == "planning_kanban"


def test_builder_yandex_badge():
    doc = build_capabilities_document(PRESET_FINANCE_ONLY, yandex_corporate_badge=True)
    assert doc["connectors"][CONNECTOR_CORPORATE_BADGE] is True


def test_env_patch_does_not_overwrite(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("TINKOFF_API_TOKEN=secret\n", encoding="utf-8")
    from shared.setup.env_patch import patch_env_file

    added = patch_env_file(env, ["TINKOFF_API_TOKEN=", "VAULT_PATH="])
    assert "VAULT_PATH=" in added
    assert "TINKOFF_API_TOKEN=" not in added
    assert "secret" in env.read_text(encoding="utf-8")


def test_planned_dirs_finance_only(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "cap.yaml"
    cfg.write_text(yaml.dump(preset_document(PRESET_FINANCE_ONLY)), encoding="utf-8")
    monkeypatch.setenv("CAPABILITIES_PATH", str(cfg))
    clear_capabilities_cache()
    prof = load_capabilities()
    dirs = [str(p.name) for p in planned_vault_dirs(prof, tmp_path / "vault")]
    assert not any("100" in d or "Задачи" in d for d in dirs)
    assert prof.module(MODULE_KNOWLEDGE) is False
