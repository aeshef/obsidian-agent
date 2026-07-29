"""Tests for kanban flow metrics aggregator."""
from __future__ import annotations

from datetime import date, datetime

from planning_bot.services.action_log_parser import is_completion_event
from planning_bot.services.kanban_flow_metrics import (
    build_task_timelines,
    compute_lead_cycle_stats,
    daily_flow_series,
    goal_mapping_week_insight,
    replay_column_snapshots_from_events,
    transition_matrix,
)


def _evt(ts: str, etype: str, data: dict) -> dict:
    return {
        "timestamp": ts,
        "dt": datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
        "type": etype,
        "data": data,
    }


def test_build_task_timelines_lead_and_cycle():
    events = [
        _evt("2026-06-01 10:00:00", "task_created", {"task_id": "a1", "title": "T"}),
        _evt("2026-06-02 10:00:00", "task_moved", {"task_id": "a1", "from": "B", "to": "IN"}),
        _evt("2026-06-05 10:00:00", "task_moved", {"task_id": "a1", "from": "IN", "to": "DONE"}),
    ]
    tl = build_task_timelines(events, in_work_column="IN", done_column="DONE")
    stats = compute_lead_cycle_stats(tl, max_lead_days=30)
    assert stats["lead_time_days"]["n"] == 1
    assert stats["cycle_time_days"]["n"] == 1
    assert stats["lead_time_days"]["p50"] == 4.0
    assert stats["cycle_time_days"]["p50"] == 3.0


def test_daily_flow_series_flow_debt():
    events = [
        _evt("2026-06-01 09:00:00", "task_created", {"task_id": "1"}),
        _evt("2026-06-01 11:00:00", "task_created", {"task_id": "2"}),
        _evt("2026-06-01 15:00:00", "task_completed", {"task_id": "1"}),
    ]
    days = [date(2026, 6, 1)]
    series = daily_flow_series(events, days)
    assert series[0]["arrivals"] == 2
    assert series[0]["departures"] == 1
    assert series[0]["flow_debt"] == 1


def test_transition_matrix():
    events = [
        _evt("2026-06-01 10:00:00", "task_moved", {"from": "A", "to": "B"}),
        _evt("2026-06-02 10:00:00", "task_moved", {"from": "A", "to": "B"}),
        _evt("2026-06-03 10:00:00", "task_moved", {"from": "B", "to": "C"}),
    ]
    m = transition_matrix(events)
    assert m["A\tB"] == 2
    assert m["B\tC"] == 1


def test_goal_mapping_week_insight_dominant_daily():
    seg_series = [
        {"date": "2026-06-01", "goal_mapped": 0, "unmapped": 1, "daily_routine": 5},
        {"date": "2026-06-02", "goal_mapped": 1, "unmapped": 0, "daily_routine": 4},
    ]
    ins = goal_mapping_week_insight(seg_series, window_days=7)
    assert ins["dominant"] == "daily_routine"
    assert ins["daily_routine_share"] > ins["goal_mapped_share"]


def test_replay_column_snapshots_end_of_day():
    events = [
        _evt("2026-06-01 10:00:00", "task_created", {"task_id": "a1", "category": "учеба"}),
        _evt("2026-06-01 15:00:00", "task_moved", {"task_id": "a1", "from": "B", "to": "IN"}),
        _evt("2026-06-02 12:00:00", "task_created", {"task_id": "a2", "category": "дом"}),
        _evt("2026-06-02 18:00:00", "task_moved", {"task_id": "a1", "from": "IN", "to": "DONE"}),
    ]
    snaps = replay_column_snapshots_from_events(
        events,
        mapping={"a1": ["g1"]},
        daily_categories=frozenset({"дом"}),
        open_columns=frozenset({"B", "IN"}),
        cat_by_id={},
        cat_by_title={},
        start_day=date(2026, 6, 1),
        end_day=date(2026, 6, 2),
        backlog_column="B",
        done_column="DONE",
    )
    assert len(snaps) == 2
    assert snaps[0]["total_open"] == 1
    assert snaps[0]["by_column"]["IN"] == 1
    assert snaps[0]["by_goal_segment"]["goal_mapped"] == 1
    assert snaps[1]["total_open"] == 1
    assert snaps[1]["by_goal_segment"]["daily_routine"] == 1


def test_replay_closes_ghosts_and_archive():
    """Ghosts (not on live board) close after last event; Archive is terminal."""
    events = [
        _evt("2026-06-01 10:00:00", "task_created", {"task_id": "keep"}),
        _evt("2026-06-01 11:00:00", "task_created", {"task_id": "ghost"}),
        _evt("2026-06-01 12:00:00", "task_moved", {"task_id": "ghost", "from": "B", "to": "IN"}),
        _evt("2026-06-02 09:00:00", "task_created", {"task_id": "arch"}),
        _evt(
            "2026-06-02 10:00:00",
            "task_moved",
            {"task_id": "arch", "from": "B", "to": "Archive"},
        ),
    ]
    snaps = replay_column_snapshots_from_events(
        events,
        mapping={},
        daily_categories=frozenset(),
        open_columns=frozenset({"B", "IN"}),
        cat_by_id={},
        cat_by_title={},
        start_day=date(2026, 6, 1),
        end_day=date(2026, 6, 3),
        backlog_column="B",
        done_column="DONE",
        live_open_ids=frozenset({"keep"}),
    )
    assert snaps[0]["by_column"].get("B", 0) == 1
    assert snaps[0]["by_column"].get("IN", 0) == 1
    assert snaps[1]["total_open"] == 1
    assert snaps[1]["by_column"].get("B", 0) == 1
    assert snaps[2]["total_open"] == 1
    assert snaps[2]["by_column"].get("B", 0) == 1
