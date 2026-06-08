"""Activity log tool formatting and limits."""
from __future__ import annotations

from datetime import date

import pytest

from planning_bot.core.config import ACTION_LOGS_DIR
from planning_bot.services.action_logger import ActionLogger
from planning_bot.services.activity_log_query import (
    clamp_activity_limit,
    fetch_activity_events,
    format_activity_events_block,
    unique_completions,
)

_FIXTURE_DAY = date(2026, 5, 12)


def _require_may_12_activity_fixture():
    """Author vault integration data; skip in CI / empty VAULT_PATH."""
    if not ACTION_LOGS_DIR.is_dir():
        pytest.skip("ACTION_LOGS_DIR missing in vault")
    logger = ActionLogger(ACTION_LOGS_DIR)
    _, _, n_raw, counts = fetch_activity_events(
        logger,
        from_date=_FIXTURE_DAY,
        to_date=_FIXTURE_DAY,
        event_types=None,
        task_id=None,
        task_title=None,
        limit=0,
    )
    if n_raw == 0 or counts.get("task_completed", 0) < 7:
        pytest.skip("2026-05-12 activity log fixture not in vault (author-only data)")
    return logger


def test_clamp_limit_max_1000():
    assert clamp_activity_limit(5000) == 1000
    assert clamp_activity_limit(0) == 0


def test_unique_completions_dedupes_move_and_complete():
    entries = [
        {
            "type": "task_moved",
            "timestamp": "2026-06-05 03:36:59",
            "data": {"title": "A", "to": "✅ Сделано", "task_id": "aa"},
        },
        {
            "type": "task_completed",
            "timestamp": "2026-06-05 03:36:59",
            "data": {"title": "A", "task_id": "aa"},
        },
        {
            "type": "task_completed",
            "timestamp": "2026-06-05 03:59:55",
            "data": {"title": "B", "task_id": "bb"},
        },
    ]
    assert len(unique_completions(entries)) == 2


def test_summary_includes_type_breakdown():
    logger = _require_may_12_activity_fixture()
    d = _FIXTURE_DAY
    entries, all_entries, n_raw, counts = fetch_activity_events(
        logger,
        from_date=d,
        to_date=d,
        event_types=None,
        task_id=None,
        task_title=None,
        limit=0,
    )
    out = format_activity_events_block(
        entries, all_entries, n_raw=n_raw, type_counts=counts, filtered_type=None
    )
    assert "completed=7" in out or "completed=7," in out
    assert "moved=104" in out
    assert "task_completed" in out
    assert "unique_completed=7" in out or "Уникальных завершённых" in out


def test_filtered_completed_only():
    logger = _require_may_12_activity_fixture()
    d = _FIXTURE_DAY
    entries, all_entries, n_raw, counts = fetch_activity_events(
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
    out = format_activity_events_block(
        entries,
        all_entries,
        n_raw=n_raw,
        type_counts=counts,
        filtered_type="task_completed",
    )
    assert "hour\tcount" in out
    assert "16\t" in out or "15\t" in out
