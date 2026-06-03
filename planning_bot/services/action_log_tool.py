"""Action log tool: one entry point for day, range, or recent chain."""
from __future__ import annotations

from typing import TYPE_CHECKING

from planning_bot.core.pdmsg import pdmsg
from shared.query.agent_interval import IntervalMode, resolve_agent_interval

if TYPE_CHECKING:
    from planning_bot.services.action_logger import ActionLogger


def format_action_log(
    logger: "ActionLogger",
    *,
    day: str = "",
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    limit: int = 0,
    default_days: int = 0,
) -> str:
    """
    day=YYYY-MM-DD → task chain for that day.
    from_date/to_date/days → chain for calendar-day range (limit=0 → full window up to safety cap).
    All empty → recent chain (hours from platform config).
    """
    interval = resolve_agent_interval(
        point_day=day,
        from_date=from_date,
        to_date=to_date,
        days=days,
        default_days=default_days if default_days > 0 else None,
    )
    lim = int(limit or 0)

    if interval.mode == IntervalMode.POINT_DAY and interval.point_day:
        return logger.get_events_chain_for_calendar_day(interval.point_day)

    if interval.mode == IntervalMode.DATE_RANGE and interval.date_range:
        dr = interval.date_range
        if dr.start and dr.end:
            return logger.get_events_chain_for_date_range(
                dr.start, dr.end, limit=lim
            )
        return pdmsg("agent_action_log_no_events")

    return logger.get_recent_events_chain(
        max_events=lim if lim > 0 else None,
    )
