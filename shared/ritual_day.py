"""Ritual calendar day: before end_hour local time counts as previous calendar day."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def calendar_day_for_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def ritual_day_for_datetime(dt: datetime, end_hour: int) -> str:
    """Local `dt` → YYYY-MM-DD ritual day (pre-end_hour → previous calendar day)."""
    hour = max(0, min(23, int(end_hour)))
    local = dt
    if local.hour < hour:
        local = local - timedelta(days=1)
    return local.strftime("%Y-%m-%d")


def parse_close_date(value: str) -> str | None:
    s = (value or "").strip()
    if _DATE_RE.match(s):
        return s
    return None
