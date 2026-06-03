"""Routines checklist for a calendar day (today file or history)."""
from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.routines_manager import (
    get_today_date,
    load_tasks_config,
    load_today_status,
)
from planning_bot.services.routines_analyzer import parse_history
from shared.parsing.iso_date import parse_iso_calendar_day


def load_status_for_day(day: str = "") -> tuple[dict, str]:
    """Status dict (morning/day/evening → task → bool) and effective YYYY-MM-DD."""
    target = parse_iso_calendar_day(day)
    today_str = get_today_date()
    if target is None:
        return load_today_status(), today_str
    key = target.isoformat()
    if key == today_str:
        return load_today_status(), key
    hist = parse_history()
    if key in hist:
        return hist[key], key
    return {"morning": {}, "day": {}, "evening": {}}, key


def format_routines_status(day: str = "") -> str:
    morning, day_t, evening = load_tasks_config()
    status, effective = load_status_for_day(day)
    lines = [pdmsg("agent_routines_header", day=effective)]
    for label, tasks, key in (
        ("Morning", morning, "morning"),
        ("Day", day_t, "day"),
        ("Evening", evening, "evening"),
    ):
        lines.append(f"\n{label}:")
        section = status.get(key) or {}
        for t in tasks:
            done = section.get(t, False)
            lines.append(f"  [{'x' if done else ' '}] {t}")
    return "\n".join(lines)
