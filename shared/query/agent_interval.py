"""Resolve point-day vs calendar-day range for agent read tools."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from shared.parsing.date_range import DateRange, resolve_date_range
from shared.parsing.iso_date import parse_iso_calendar_day


class IntervalMode(str, Enum):
    POINT_DAY = "point_day"
    DATE_RANGE = "date_range"
    DEFAULT = "default"


@dataclass(frozen=True)
class AgentInterval:
    mode: IntervalMode
    point_day: Optional[date] = None
    date_range: Optional[DateRange] = None


def resolve_agent_interval(
    *,
    point_day: str = "",
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    default_days: int | None = None,
    anchor: date | None = None,
) -> AgentInterval:
    """
    point_day: YYYY-MM-DD — single calendar day (wins over range).
    from_date / to_date / days: inclusive calendar-day range via resolve_date_range.
    All empty → DEFAULT (caller uses tool-specific fallback, e.g. upcoming calendar).
    """
    cal = parse_iso_calendar_day(point_day)
    if cal is not None:
        return AgentInterval(IntervalMode.POINT_DAY, point_day=cal)

    has_range = bool(
        (from_date or "").strip()
        or (to_date or "").strip()
        or (days and int(days) > 0)
        or (default_days and int(default_days) > 0)
    )
    if has_range:
        dr = resolve_date_range(
            from_date=from_date,
            to_date=to_date,
            days=days,
            default_days=default_days,
            anchor=anchor,
        )
        return AgentInterval(IntervalMode.DATE_RANGE, date_range=dr)

    return AgentInterval(IntervalMode.DEFAULT)
