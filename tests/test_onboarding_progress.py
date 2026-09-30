"""Onboarding progress, status import, intro defaults."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from shared.capabilities.onboarding_defaults import intro_default_for
from shared.capabilities.onboarding_progress import PHASES, collect_progress
from shared.capabilities.presets import PRESET_PLANNING_ONLY, preset_document
from shared.capabilities.profile import clear_capabilities_cache, profile_from_document


@pytest.fixture(autouse=True)
def _clear_cap(monkeypatch):
    monkeypatch.delenv("CAPABILITIES_PATH", raising=False)
    clear_capabilities_cache()
    yield
    clear_capabilities_cache()


def test_onboarding_status_imports():
    from shared.capabilities.onboarding_status import collect_status, format_status_text

    assert callable(collect_status)
    assert callable(format_status_text)


def test_bootstrap_phase_order_vault_before_layout():
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load(
        (root / "config/agent/bootstrap_checklist.yaml.example").read_text(encoding="utf-8")
    )
    ids = [p["id"] for p in data["phases"]]
    assert ids.index("vault_path") < ids.index("vault_layout")
    assert ids.index("capabilities") < ids.index("vault_layout")
    assert ids.index("venv_bootstrap") < ids.index("capabilities")
    assert "interview_intro" in ids
    assert ids.index("interview_intro") < ids.index("vault_layout")


def test_intro_defaults_planning_only():
    prof = profile_from_document(preset_document(PRESET_PLANNING_ONLY))
    assert intro_default_for("user_about", "en", prof) is not None
    assert intro_default_for("finance_accounts", "en", prof) is None
    tone = intro_default_for("user_tone", "en", prof)
    assert tone and tone.get("choice_index") == 1


def test_collect_progress_has_percent(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "capabilities.yaml"
    cfg.write_text(yaml.dump(preset_document(PRESET_PLANNING_ONLY)), encoding="utf-8")
    monkeypatch.setenv("CAPABILITIES_PATH", str(cfg))
    clear_capabilities_cache()
    prof = profile_from_document(preset_document(PRESET_PLANNING_ONLY))
    data = collect_progress(prof, locale="en")
    assert data["total"] == len(PHASES)
    assert 0 <= data["percent"] <= 100
    assert data["next_phase"]


def test_apply_intro_defaults_cli(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    agent_cfg = tmp_path / "agent"
    agent_cfg.mkdir()
    (agent_cfg / "capabilities.yaml").write_text(
        yaml.dump(preset_document(PRESET_PLANNING_ONLY)), encoding="utf-8"
    )
    (agent_cfg / "onboarding_state.yaml").write_text("completed: []\nanswers: {}\n", encoding="utf-8")
    (agent_cfg / "onboarding_slots.yaml").write_text("USER_LOCALE: en\n", encoding="utf-8")
    monkeypatch.setenv("CAPABILITIES_PATH", str(agent_cfg / "capabilities.yaml"))
    monkeypatch.setenv("AGENT_CONFIG_DIR", str(agent_cfg))
    clear_capabilities_cache()

    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, str(repo / "scripts/onboarding_interview.py"), "apply-intro-defaults"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "applied intro defaults" in r.stdout or "nothing to apply" in r.stdout
