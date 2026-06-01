"""ISO date ranges for agent tools (from/to/days — no relative dates in code)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from shared.parsing.iso_date import parse_iso_calendar_day


@dataclass(frozen=True)
class DateRange:
    start: date | None
    end: date | None

    def contains(self, d: date) -> bool:
        if self.start and d < self.start:
            return False
        if self.end and d > self.end:
            return False
        return True


def resolve_date_range(
    *,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    default_days: int | None = None,
    anchor: date | None = None,
) -> DateRange:
    """
    from_date/to_date: YYYY-MM-DD (empty = unset).
    days: last N days including anchor (when from/to empty).
    default_days: when all empty.
    """
    today = anchor or date.today()
    start = parse_iso_calendar_day(from_date)
    end = parse_iso_calendar_day(to_date)

    if start and end and start > end:
        start, end = end, start

    if start is None and end is None:
        n = int(days) if days and int(days) > 0 else (default_days or 0)
        if n > 0:
            end = today
            start = today - timedelta(days=n - 1)
    elif start is None and end is not None:
        start = end
    elif start is not None and end is None:
        end = today if start <= today else start

    return DateRange(start=start, end=end)
