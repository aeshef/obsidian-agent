"""Activity log tool formatting and limits."""
from __future__ import annotations

from datetime import date

from planning_bot.core.config import ACTION_LOGS_DIR
from planning_bot.services.action_logger import ActionLogger
from planning_bot.services.activity_log_query import (
    clamp_activity_limit,
    fetch_activity_events,
    format_activity_events_block,
)


def test_clamp_limit_max_1000():
    assert clamp_activity_limit(5000) == 1000
    assert clamp_activity_limit(0) == 0


def test_summary_includes_type_breakdown():
    logger = ActionLogger(ACTION_LOGS_DIR)
    d = date(2026, 5, 12)
    entries, n_raw, counts = fetch_activity_events(
        logger,
        from_date=d,
        to_date=d,
        event_types=None,
        task_id=None,
        task_title=None,
        limit=0,
    )
    out = format_activity_events_block(entries, n_raw=n_raw, type_counts=counts, filtered_type=None)
    assert "completed=7" in out or "completed=7," in out
    assert "moved=104" in out
    assert "task_completed" in out


def test_filtered_completed_only():
    logger = ActionLogger(ACTION_LOGS_DIR)
    d = date(2026, 5, 12)
    entries, n_raw, counts = fetch_activity_events(
        logger,
        from_date=d,
        to_date=d,
        event_types={"task_completed"},
        task_id=None,
        task_title=None,
        limit=0,
    )
    assert n_raw == len(entries) == 7
    assert counts == {"task_completed": 7}
