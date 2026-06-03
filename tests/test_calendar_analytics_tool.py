"""Calendar analytics agent output includes per-day rows."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.calendar_analytics import compute_week_analytics


def test_daily_rows_pdmsg_non_empty():
    assert pdmsg("agent_calendar_analytics_daily_row", date="2026-06-01", weekday="пн", meetings=3, minutes=120).strip()


def test_compute_week_has_days():
    ev = [
        {
            "date": "2026-06-01",
            "start": "10:00",
            "end": "11:00",
            "title": "A",
            "is_allday": False,
            "is_cancelled": False,
        }
    ]
    a = compute_week_analytics(ev, date(2026, 6, 1), horizon_days=1)
    assert a["days"][0]["meeting_minutes"] == 60
