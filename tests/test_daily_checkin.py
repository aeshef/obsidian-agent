"""Daily check-in: config, routines toggle, signals history."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def vault_env(tmp_path, monkeypatch):
    routines = tmp_path / "400_Routines"
    sub = routines / "Routines"
    sub.mkdir(parents=True)
    (sub / "Tasks_Config.md").write_text(
        "## Evening\n\n- Brush teeth\n",
        encoding="utf-8",
    )
    today = sub / "Today.md"
    today.write_text(
        "## Evening\n\n- [ ] Brush teeth\n\n---\n\n**Date:** 2099-01-01\n",
        encoding="utf-8",
    )
    cfg = {
        "folders": {"routines": "400_Routines"},
        "files": {
            "signals_subdir": "Signals/",
            "signals_config_yaml": "Signals_Config.yaml",
            "signals_history_md": "Signals_History.md",
            "routines_calendar_subdir": "Routines/",
            "routines_stats_md": "Routine_stats.md",
        },
    }
    (ROOT / "config" / "vault_paths.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("AGENT_LOCALE", "en")
    yield tmp_path
    vp = ROOT / "config" / "vault_paths.yaml"
    if vp.is_file():
        vp.unlink()


def test_daily_checkin_config_loads():
    from planning_bot.services.daily_checkin_config import (
        load_daily_checkin_config,
        routine_sections_order,
        signals_config,
    )

    load_daily_checkin_config.cache_clear()
    cfg = load_daily_checkin_config()
    assert "checkin" in cfg
    assert "evening" in routine_sections_order()
    assert any(s.get("id") == "mood" for s in signals_config())


def test_set_task_done(vault_env, monkeypatch):
    from planning_bot.services import routines_manager as rm

    def _pdmsg(key, **kw):
        return {
            "auto_9e515fb7c8": "400_Routines",
            "auto_fc906f665b": "Routines/",
            "auto_f9a9071bae": "Tasks_Config.md",
            "auto_2cc3b7c2af": "Today.md",
            "auto_1c178f6429": "History.md",
            "auto_87b10eda1f": "## Morning",
            "auto_3ed8660b4d": "## Day",
            "auto_0f1e39b138": "## Evening",
        }.get(key, key)

    monkeypatch.setattr(rm, "pdmsg", _pdmsg)
    rm.ROUTINES_DIR = vault_env / "400_Routines" / "Routines"
    rm.TODAY_FILE = rm.ROUTINES_DIR / "Today.md"
    assert rm.set_task_done("evening", "Brush teeth", True)
    text = rm.TODAY_FILE.read_text(encoding="utf-8")
    assert "- [x] Brush teeth" in text


def test_append_signals_entry(vault_env, monkeypatch):
    from planning_bot.services import signals_manager as sm

    monkeypatch.setenv("AGENT_LOCALE", "en")
    sm.append_signals_entry({"mood": 5, "energy": 3}, date_str="2099-06-01")
    path = vault_env / "400_Routines" / "Signals" / "Signals_History.md"
    assert path.is_file()
    body = path.read_text(encoding="utf-8")
    assert "## 2099-06-01" in body
    assert "mood: 5" in body


def test_text_trigger_close_day(monkeypatch):
    from planning_bot.app.ui import pmsg
    from planning_bot.services.planning_text_triggers import (
        clear_planning_text_triggers_cache,
        match_planning_text_trigger,
    )

    clear_planning_text_triggers_cache()
    phrase = pmsg("checkin_phrase_close_day")
    if phrase:
        assert match_planning_text_trigger(phrase) == "start_daily_checkin"
    assert match_planning_text_trigger("random unrelated phrase xyz") is None


def test_start_daily_checkin_bound_as_planning_bot_method():
    """Menu dispatch calls bot.start_daily_checkin(msg, state) — needs self like start_reflection."""
    import inspect

    from planning_bot.app.bot import PlanningBot
    from planning_bot.app.handlers import daily_checkin

    sig = inspect.signature(daily_checkin.start_daily_checkin)
    params = list(sig.parameters)
    assert params[0] == "self"
    assert hasattr(PlanningBot, "start_daily_checkin")
    assert PlanningBot.start_daily_checkin is daily_checkin.start_daily_checkin


def test_planning_daily_checkin_feature_default():
    from shared.capabilities.features import (
        FEAT_PLANNING_DAILY_CHECKIN,
        FEAT_PLANNING_ROUTINES,
        feature_enabled,
    )
    from shared.capabilities.profile import CapabilityProfile, MODULE_PLANNING

    prof = CapabilityProfile(
        modules={MODULE_PLANNING: True},
        connectors={},
        feature_overrides={},
        sync_profile="full",
    )
    assert feature_enabled(FEAT_PLANNING_ROUTINES, prof)
    assert feature_enabled(FEAT_PLANNING_DAILY_CHECKIN, prof)
