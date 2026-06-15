"""Ritual day date for routines and daily check-in."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from shared.ritual_day import calendar_day_for_datetime, parse_close_date, ritual_day_for_datetime


def test_ritual_day_before_end_hour_is_yesterday():
    tz = ZoneInfo("Europe/Moscow")
    dt = datetime(2026, 6, 14, 2, 30, tzinfo=tz)
    assert calendar_day_for_datetime(dt) == "2026-06-14"
    assert ritual_day_for_datetime(dt, 4) == "2026-06-13"


def test_ritual_day_after_end_hour_is_today():
    tz = ZoneInfo("Europe/Moscow")
    dt = datetime(2026, 6, 14, 5, 0, tzinfo=tz)
    assert ritual_day_for_datetime(dt, 4) == "2026-06-14"


def test_parse_close_date():
    assert parse_close_date("2026-06-13") == "2026-06-13"
    assert parse_close_date("bad") is None


def test_ritual_day_service(monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "en")
    from planning_bot.services.daily_checkin_config import load_daily_checkin_config

    load_daily_checkin_config.cache_clear()
    from planning_bot.services.ritual_day import calendar_day_date, ritual_day_date

    tz = ZoneInfo("Europe/Moscow")
    fixed = datetime(2026, 6, 13, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return fixed.astimezone(tz)
            return fixed

    monkeypatch.setattr("planning_bot.services.ritual_day.datetime", _FixedDatetime)
    monkeypatch.setattr("planning_bot.services.ritual_day.get_tz", lambda: tz)
    assert calendar_day_date() == "2026-06-14"
    assert ritual_day_date() == "2026-06-13"


def test_checkin_state_uses_ritual_day(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_LOCALE", "en")
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    tz = ZoneInfo("Europe/Moscow")
    fixed = datetime(2026, 6, 13, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return fixed.astimezone(tz)
            return fixed

    from planning_bot.services.daily_checkin_config import load_daily_checkin_config

    load_daily_checkin_config.cache_clear()
    monkeypatch.setattr("planning_bot.services.ritual_day.datetime", _FixedDatetime)
    monkeypatch.setattr("planning_bot.services.ritual_day.get_tz", lambda: tz)

    from planning_bot.services.checkin_state import (
        completed_for_today,
        mark_completed,
        should_send_scheduled_prompt,
    )

    assert not completed_for_today()
    mark_completed("2026-06-13")
    assert completed_for_today()
    assert not should_send_scheduled_prompt()


def test_checkin_state_early_close_still_gets_evening_prompt(monkeypatch, tmp_path):
    """Manual close before 23:45 offer should not block scheduled evening prompt."""
    monkeypatch.setenv("AGENT_LOCALE", "en")
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    tz = ZoneInfo("Europe/Moscow")
    fixed = datetime(2026, 6, 14, 23, 45, tzinfo=timezone.utc).astimezone(tz)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return fixed.astimezone(tz)
            return fixed

    from planning_bot.services.daily_checkin_config import load_daily_checkin_config

    load_daily_checkin_config.cache_clear()
    monkeypatch.setattr("planning_bot.services.ritual_day.datetime", _FixedDatetime)
    monkeypatch.setattr("planning_bot.services.ritual_day.get_tz", lambda: tz)
    monkeypatch.setattr("planning_bot.services.checkin_state.datetime", _FixedDatetime)
    monkeypatch.setattr("planning_bot.services.checkin_state.get_tz", lambda: tz)

    from planning_bot.services.checkin_state import mark_completed, should_send_scheduled_prompt

    mark_completed("2026-06-14")
    assert should_send_scheduled_prompt()
