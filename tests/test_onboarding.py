"""Presets, builder, vault layout planning."""
from __future__ import annotations

import os
import sys
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
from shared.capabilities.prompt_dirs import prompt_dirs_for_profile
from shared.capabilities.profile import profile_from_document
from shared.capabilities.vault_init import planned_vault_dirs
from shared.capabilities.vault_paths_locale import (
    is_default_en_vault_paths,
    should_replace_vault_paths_for_locale,
)


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


def test_prompt_dirs_finance_only():
    prof = profile_from_document(preset_document(PRESET_FINANCE_ONLY))
    dirs = prompt_dirs_for_profile(prof)
    assert "finance_bot/config/prompts" in dirs
    assert "planning_bot/config/prompts" not in dirs
    assert "knowledge_bot/config/prompts" not in dirs


def test_vault_paths_locale_replace():
    en_doc = {"folders": {"tasks": "100_Tasks", "goals": "200_Goals", "dashboards": "300_Dashboards", "routines": "400_Routines", "handwritten": "600_Handwritten"}}
    assert is_default_en_vault_paths(en_doc)
    assert should_replace_vault_paths_for_locale(en_doc, "ru")


def test_planned_dirs_finance_only(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "cap.yaml"
    cfg.write_text(yaml.dump(preset_document(PRESET_FINANCE_ONLY)), encoding="utf-8")
    monkeypatch.setenv("CAPABILITIES_PATH", str(cfg))
    clear_capabilities_cache()
    prof = load_capabilities()
    dirs = [str(p.name) for p in planned_vault_dirs(prof, tmp_path / "vault")]
    assert not any("100" in d or "Задачи" in d for d in dirs)
    assert prof.module(MODULE_KNOWLEDGE) is False
    assert not any("Knowledge" in str(p) for p in dirs)


def test_init_vault_layout_requires_capabilities(tmp_path: Path, monkeypatch):
    import subprocess

    repo = Path(__file__).resolve().parents[1]
    vault = tmp_path / "vault"
    vault.mkdir()
    env = {"VAULT_PATH": str(vault), "CAPABILITIES_PATH": str(tmp_path / "missing.yaml")}
    r = subprocess.run(
        [sys.executable, str(repo / "scripts/init_vault_layout.py")],
        cwd=repo,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert "capabilities.yaml missing" in r.stderr
