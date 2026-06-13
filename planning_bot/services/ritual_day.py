"""Ritual day for routines/check-in (config-driven end_hour)."""
from __future__ import annotations

from datetime import datetime, timezone

from planning_bot.services.daily_checkin_config import ritual_day_end_hour
from shared.ritual_day import calendar_day_for_datetime, ritual_day_for_datetime
from shared.tz import get_tz


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone(get_tz())


def calendar_day_date() -> str:
    return calendar_day_for_datetime(now_local())


def ritual_day_date() -> str:
    return ritual_day_for_datetime(now_local(), ritual_day_end_hour())


def ritual_day_active() -> bool:
    return calendar_day_date() != ritual_day_date()
