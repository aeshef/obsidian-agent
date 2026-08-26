"""Unified interval tools: calendar range, action log range, routines day."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from planning_bot.core.config import ACTION_LOGS_DIR
from planning_bot.services.action_log import ActionLogger
from planning_bot.services.action_log_tool import format_action_log
from planning_bot.services.calendar_service import get_calendar_for_tool, get_events_in_range_text
from planning_bot.services.routines_status_query import load_status_for_day
from shared.query.agent_interval import IntervalMode, resolve_agent_interval


def test_resolve_point_day_wins():
    iv = resolve_agent_interval(point_day="2026-06-01", from_date="2026-05-01", to_date="2026-05-31")
    assert iv.mode == IntervalMode.POINT_DAY
    assert iv.point_day == date(2026, 6, 1)


def test_resolve_date_range():
    iv = resolve_agent_interval(from_date="2026-06-01", to_date="2026-06-03")
    assert iv.mode == IntervalMode.DATE_RANGE
    assert iv.date_range and iv.date_range.start == date(2026, 6, 1)
    assert iv.date_range.end == date(2026, 6, 3)


def test_calendar_range_lists_events(tmp_path):
    p = tmp_path / "cal.json"
    p.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "date": "2026-06-01",
                        "start": "10:00",
                        "end": "11:00",
                        "title": "A",
                        "is_allday": False,
                        "is_cancelled": False,
                    },
                    {
                        "date": "2026-06-02",
                        "start": "12:00",
                        "end": "13:00",
                        "title": "B",
                        "is_allday": False,
                        "is_cancelled": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    out = get_events_in_range_text(p, date(2026, 6, 1), date(2026, 6, 2))
    assert "A" in out and "B" in out
    tool = get_calendar_for_tool(
        p, from_date="2026-06-01", to_date="2026-06-02", max_chars=8000
    )
    assert "A" in tool and "B" in tool


def test_action_log_range_has_period_line():
    logger = ActionLogger(ACTION_LOGS_DIR)
    out = format_action_log(
        logger,
        from_date="2026-05-12",
        to_date="2026-05-12",
        limit=5,
    )
    assert "2026-05-12" in out
    assert "task_" in out or "Событий" in out or "Период" in out


def test_load_routines_status_today_is_dict():
    status, effective = load_status_for_day("")
    assert effective
    assert "morning" in status
