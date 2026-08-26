"""Date / chart-window helpers for finance dashboard charts."""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Iterable


def series_floor(dates: Iterable[date], *, fallback: date) -> date:
    dated = list(dates)
    return min(dated) if dated else fallback


def chart_window_int(key: str, env_key: str, legacy: int) -> int:
    """Resolve chart window from templates, then env, then legacy default."""
    from bot.dashboard_templates import dtpl_raw

    cw = dtpl_raw("chart_windows")
    if isinstance(cw, dict) and key in cw and cw[key] is not None:
        try:
            return int(cw[key])
        except (TypeError, ValueError):
            pass
    env_raw = os.environ.get(env_key, "").strip()
    if env_raw:
        try:
            return int(env_raw)
        except ValueError:
            pass
    return legacy


def day_range(end: date, floor: date, window_days: int) -> list[date]:
    if window_days > 0:
        start = max(floor, end - timedelta(days=window_days - 1))
    else:
        start = floor
    if start > end:
        return [end]
    span = (end - start).days + 1
    return [start + timedelta(days=i) for i in range(span)]


def week_range(week_end: date, floor: date, max_weeks: int) -> list[date]:
    weeks: list[date] = []
    cur = week_end
    while cur >= floor:
        weeks.append(cur)
        if max_weeks > 0 and len(weeks) >= max_weeks:
            break
        cur = cur - timedelta(days=7)
    weeks.reverse()
    return weeks


def format_day_labels(days: list[date]) -> list[str]:
    if len(days) > 120:
        return [d.strftime("%m.%y") if d.day == 1 else "" for d in days]
    if len(days) > 60:
        return [d.strftime("%d.%m.%y") for d in days]
    return [d.strftime("%d.%m") for d in days]


def spending_axis_end(spending_dates: set[date], *, today: date) -> date:
    """Spending chart axis end: last day with data (+ up to 3 days to today)."""
    if not spending_dates:
        return today
    last = max(spending_dates)
    if last < today and (today - last).days <= 3:
        return today
    return last
