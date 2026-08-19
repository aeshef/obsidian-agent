"""Timezone-safe timestamp compare and load-window sizing (any snapshot/log dir)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def parse_iso_dt(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime.combine(raw, datetime.min.time())
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.replace(" ", "T", 1)
    for cand in (s[:32], s[:26], s[:19], s[:16], s[:10]):
        try:
            return datetime.fromisoformat(cand)
        except ValueError:
            continue
    return None


def align_tz(a: datetime, b: datetime) -> tuple[datetime, datetime]:
    if a.tzinfo is not None and b.tzinfo is None:
        b = b.replace(tzinfo=a.tzinfo)
    elif a.tzinfo is None and b.tzinfo is not None:
        a = a.replace(tzinfo=b.tzinfo)
    return a, b


def dt_ge(a: datetime, b: datetime) -> bool:
    x, y = align_tz(a, b)
    return x >= y


def dt_gt(a: datetime, b: datetime) -> bool:
    x, y = align_tz(a, b)
    return x > y


def dt_lt(a: datetime, b: datetime) -> bool:
    x, y = align_tz(a, b)
    return x < y


def as_naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def days_covering(
    start: datetime | date,
    *,
    now: datetime | None = None,
    extra: int = 3,
    cap: int = 400,
) -> int:
    """How many trailing calendar days to load so `start` is inside the cutoff."""
    now = now or datetime.now()
    if isinstance(start, datetime):
        s = as_naive(start)
    else:
        s = datetime.combine(start, datetime.min.time())
    n = (as_naive(now) - s).days + max(1, int(extra))
    return max(1, min(int(cap or 400), n))


def snapshot_load_days(
    start: datetime | date | None,
    *,
    now: datetime | None = None,
    floor: int = 14,
    extra: int = 3,
    cap: int = 400,
) -> int:
    """Trailing-day load window for any snapshot dir. Sized from `start` to now, not from span length."""
    floor_n = max(1, int(floor or 1))
    cap_n = max(floor_n, int(cap or 400))
    if start is None:
        return min(cap_n, floor_n)
    return max(floor_n, days_covering(start, now=now, extra=extra, cap=cap_n))


def day_bounds(
    start: date | datetime | None,
    end: date | datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Inclusive calendar-day window as naive datetimes (00:00 … 23:59:59)."""
    def _as_date(value: date | datetime | None) -> date | None:
        if value is None:
            return None
        return value.date() if isinstance(value, datetime) else value

    s = _as_date(start)
    e = _as_date(end if end is not None else start)
    req_s = datetime.combine(s, datetime.min.time()) if s else None
    req_e = (
        datetime.combine(e, datetime.max.time()).replace(microsecond=0) if e else None
    )
    return req_s, req_e
