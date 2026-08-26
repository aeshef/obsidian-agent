"""Top-level kanban flow metrics aggregation."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from planning_bot.core.config import DONE_COLUMN, IN_WORK_COLUMN, KANBAN_COLUMNS
from planning_bot.services.action_log_parser import collect_events_from_logs
from planning_bot.services.kanban_flow.history import _iter_days
from planning_bot.services.kanban_flow.insights import (
    blocked_ratio_snapshot,
    deadline_blitz_stats,
    goal_mapping_week_insight,
    weekly_lead_cycle_series,
)
from planning_bot.services.kanban_flow.replay import (
    build_column_history,
    infer_reliable_start_day,
)
from planning_bot.services.kanban_flow.timelines import (
    aging_open_tasks,
    build_task_timelines,
    completions_by_segment_series,
    compute_lead_cycle_stats,
    daily_flow_series,
    transition_matrix,
    weekly_throughput_series,
)
from planning_bot.services.kanban_flow.window import _flow_cfg
from shared.goals.task_segment import (
    SEGMENT_DAILY_ROUTINE,
    SEGMENT_GOAL_MAPPED,
    SEGMENT_UNMAPPED,
    flow_daily_categories,
)


def compute_kanban_flow_metrics(
    vault: Path,
    *,
    action_logs_dir: Path,
    column_history_path: Path,
    kanban_schema: dict,
    mapping: Dict[str, List[str]],
    board_tasks: Sequence[dict],
    cat_by_id: Dict[str, str],
    cat_by_title: Dict[str, str],
    backfill_columns: bool = False,
    allow_auto_backfill: bool = True,
    trusted_open_totals: Optional[Dict[str, int]] = None,
) -> Tuple[dict[str, Any], List[dict]]:
    cfg = _flow_cfg()
    daily_cats = flow_daily_categories(kanban_schema)

    events = collect_events_from_logs(action_logs_dir)
    stable = [e for e in events if (e.get("data") or {}).get("task_id")]
    metrics_start = infer_reliable_start_day(events, cfg)
    if metrics_start is not None:
        events_eff = [e for e in events if e.get("dt") and e["dt"].date() >= metrics_start]
    else:
        events_eff = list(events)
    stable_eff = [e for e in events_eff if (e.get("data") or {}).get("task_id")]

    history, col_meta = build_column_history(
        events=events,
        column_history_path=column_history_path,
        kanban_schema=kanban_schema,
        mapping=mapping,
        board_tasks=board_tasks,
        cat_by_id=cat_by_id,
        cat_by_title=cat_by_title,
        backfill_columns=backfill_columns,
        allow_auto_backfill=allow_auto_backfill,
        trusted_open_totals=trusted_open_totals,
    )
    snap = next(
        (s for s in reversed(history) if s.get("date") == date.today().isoformat()),
        history[-1] if history else {},
    )

    if not stable_eff:
        empty = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "no_task_id_events",
            "column_snapshot": snap,
            "column_history_days": len(history),
            "column_history_meta": col_meta,
        }
        return empty, history

    start_day = min(e["dt"].date() for e in stable_eff)
    end_day = date.today()
    days = _iter_days(start_day, end_day)

    timelines = build_task_timelines(
        events_eff,
        in_work_column=IN_WORK_COLUMN,
        done_column=DONE_COLUMN,
    )
    daily = daily_flow_series(events_eff, days)
    weekly_tp = weekly_throughput_series(events_eff, days)
    seg_series = completions_by_segment_series(
        events_eff,
        days,
        mapping=mapping,
        daily_categories=daily_cats,
        cat_by_id=cat_by_id,
        cat_by_title=cat_by_title,
    )
    lead_cycle = compute_lead_cycle_stats(
        timelines, max_lead_days=cfg["lead_time_max_days"]
    )
    weekly_lc = weekly_lead_cycle_series(
        timelines, days, max_lead_days=cfg["lead_time_max_days"]
    )
    transitions = transition_matrix(events_eff)
    aging = aging_open_tasks(
        board_tasks, today=end_day, stale_days=cfg["aging_stale_days"]
    )
    deadline_blitz = deadline_blitz_stats(timelines, board_tasks)
    blocked = blocked_ratio_snapshot(
        board_tasks,
        blocked_column=KANBAN_COLUMNS[4] if len(KANBAN_COLUMNS) > 4 else "",
    )
    insight = goal_mapping_week_insight(seg_series, window_days=cfg["rolling_window_days"])

    total_completions = sum(int(r.get("departures", 0)) for r in daily)
    coverage = lead_cycle["completed_with_task_id"]
    n_events = len(events_eff)
    n_events_raw = len(events)

    metrics: dict[str, Any] = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "ok",
        "period": {"start": start_day.isoformat(), "end": end_day.isoformat()},
        "coverage": {
            "events": n_events,
            "events_with_task_id": len(stable_eff),
            "task_id_coverage_pct": round(100.0 * len(stable_eff) / max(1, n_events), 1),
            "completed_with_task_id": coverage,
            "events_raw": n_events_raw,
            "metrics_start": metrics_start.isoformat() if metrics_start else None,
        },
        "summary": {
            "total_completions": total_completions,
            "current_open": snap["total_open"],
            "flow_debt_today": daily[-1]["flow_debt"] if daily else 0,
            "blocked_ratio": blocked["ratio"],
            "lead_time_p50_days": lead_cycle["lead_time_days"]["p50"],
            "cycle_time_p50_days": lead_cycle["cycle_time_days"]["p50"],
            "stale_open_count": aging["stale_count"],
            "week_dominant_segment": insight.get("dominant"),
            "week_goal_mapped_share": insight.get("goal_mapped_share"),
            "week_daily_routine_share": insight.get("daily_routine_share"),
        },
        "daily_flow": daily,
        "weekly_throughput": weekly_tp,
        "completions_by_goal_segment": seg_series,
        "weekly_lead_cycle": weekly_lc,
        "lead_cycle_stats": lead_cycle,
        "transitions": transitions,
        "aging": aging,
        "deadline_blitz": deadline_blitz,
        "blocked": blocked,
        "goal_mapping_insight": insight,
        "column_snapshot": snap,
        "column_history_days": len(history),
        "column_history_meta": col_meta,
        "segments": {
            "goal_mapped": SEGMENT_GOAL_MAPPED,
            "unmapped": SEGMENT_UNMAPPED,
            "daily_routine": SEGMENT_DAILY_ROUTINE,
        },
        "daily_routine_categories": sorted(daily_cats),
    }
    return metrics, history
