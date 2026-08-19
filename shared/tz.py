"""Unified timezone handling (zoneinfo + env TIMEZONE)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Optional

from shared.constants import timezone_name


@lru_cache(maxsize=16)
def get_tz(name: Optional[str] = None):
    """ZoneInfo for IANA name; fallback UTC."""
    tzname = timezone_name(override=name)
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tzname)
    except Exception:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo("UTC")
        except Exception:
            return timezone.utc


def now_in_tz(name: Optional[str] = None) -> datetime:
    return datetime.now(get_tz(name))


def today_in_tz(name: Optional[str] = None) -> date:
    return now_in_tz(name).date()


def format_local_ts(iso: str, *, name: Optional[str] = None) -> str:
    """Stored UTC (or any ISO) timestamp as local wall clock for prompts. Empty if unparseable."""
    raw = (iso or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_tz(name)).strftime("%Y-%m-%d %H:%M")
