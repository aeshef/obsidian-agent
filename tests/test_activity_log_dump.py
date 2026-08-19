"""Activity log dump uses the shared coverage contract."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from planning_bot.services.activity_log_query import format_activity_events_block, format_task_event_dump


def _evt(i: int, kind: str) -> dict:
    ts = datetime(2026, 8, 1, 10, 0, 0) + timedelta(minutes=i)
    return {
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "type": kind,
        "data": {"title": f"T{i}", "task_id": f"id{i}"},
    }


def test_activity_dump_shares_cover_all_not_tail():
    matched = [_evt(i, "task_completed" if i % 3 == 0 else "task_moved") for i in range(12)]
    display = matched[-3:]
    out = format_task_event_dump(
        display,
        matched,
        requested_start=datetime(2026, 8, 1, 0, 0, 0),
        requested_end=datetime(2026, 8, 1, 23, 59, 0),
        title="period",
        slice_kind="tail",
    )
    assert "n=12" in out
    assert "task_moved" in out
    assert out.index("n=12") < out.index(display[0]["timestamp"])


def test_activity_block_keeps_type_summary():
    matched = [_evt(i, "task_completed") for i in range(4)]
    out = format_activity_events_block(
        matched,
        matched,
        n_raw=4,
        type_counts={"task_completed": 4},
        filtered_type=None,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 1),
    )
    assert "completed=4" in out
    assert "n=4" in out
