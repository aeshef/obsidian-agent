"""Daily check-in: config, routines toggle, signals history."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def vault_env(tmp_path, monkeypatch):
    routines = tmp_path / "400_Routines"
    op = routines / "Routines"
    data = routines / "Data"
    op.mkdir(parents=True)
    data.mkdir(parents=True)
    (op / "Tasks_Config.md").write_text(
        "## Evening routines\n\n- Brush teeth\n",
        encoding="utf-8",
    )
    cfg = {
        "folders": {"routines": "400_Routines"},
        "routines": {
            "operational": "Routines",
            "signals": "Signals",
            "data": "Data",
            "charts": "Charts",
            "charts_routines": "Routines",
            "charts_signals": "Signals",
        },
        "files": {
            "signals_subdir": "Signals/",
            "signals_config_md": "Signals_Config.md",
            "signals_config_yaml": "Signals_Config.yaml",
            "signals_history_md": "Signals_History.md",
            "signals_stats_md": "Charts/Signals/Signals_statistics.md",
            "routines_calendar_subdir": "Routines/",
            "routines_config_md": "Tasks_Config.md",
            "routines_history_md": "Routines_History.md",
            "routines_today_json": "routines_today.json",
            "routines_today_legacy_md": "Today.md",
            "routines_stats_md": "Charts/Routines/Routine_statistics.md",
            "routines_stats_legacy_md": "Routine_statistics.md",
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


def test_set_task_done(vault_env):
    from planning_bot.services.routines_config import section_config_header
    from planning_bot.services.routines_manager import set_task_done
    from shared.routines_paths import routines_config_path, routines_today_json_path

    routines_config_path().write_text(
        f"{section_config_header('evening')}\n\n- Brush teeth\n",
        encoding="utf-8",
    )
    assert set_task_done("evening", "Brush teeth", True)
    payload = json.loads(routines_today_json_path().read_text(encoding="utf-8"))
    assert payload["status"]["evening"]["Brush teeth"] is True


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
