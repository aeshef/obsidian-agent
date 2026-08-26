"""Deadline blitz, blocked ratio, weekly lead/cycle, goal-mapping insights."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Sequence

import numpy as np

from planning_bot.core.config import KANBAN_COLUMNS
from shared.goals.task_segment import (
    ALL_SEGMENTS,
    SEGMENT_DAILY_ROUTINE,
    SEGMENT_GOAL_MAPPED,
    SEGMENT_UNMAPPED,
)


def deadline_blitz_stats(
    timelines: Dict[str, dict],
    board_tasks: Sequence[dict],
) -> dict[str, Any]:
    """Classify completed tasks vs deadline: on_day / early / late / no_deadline."""
    deadlines: dict[str, date] = {}
    for t in board_tasks:
        tid = (t.get("task_id") or "").strip()
        if not tid:
            continue
        raw = (t.get("deadline") or "").strip()
        if not raw:
            continue
        try:
            deadlines[tid.lower()] = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

    counts = {"on_day": 0, "early": 0, "late": 0, "no_deadline": 0}
    for tid, tl in timelines.items():
        if not tl.get("done_at"):
            continue
        done_d = tl["done_at"].date() if hasattr(tl["done_at"], "date") else None
        if done_d is None:
            continue
        # Timeline dict keys are "id:{task_id}"; deadlines map uses raw task_id.
        raw_tid = (tl.get("task_id") or "").strip().lower()
        if not raw_tid and isinstance(tid, str) and tid.startswith("id:"):
            raw_tid = tid[3:].strip().lower()
        dl = deadlines.get(raw_tid) if raw_tid else None
        if dl is None:
            counts["no_deadline"] += 1
        elif done_d == dl:
            counts["on_day"] += 1
        elif done_d < dl:
            counts["early"] += 1
        else:
            counts["late"] += 1
    total = sum(counts.values())
    with_dl = counts["on_day"] + counts["early"] + counts["late"]
    return {
        "counts": counts,
        "total": total,
        "with_deadline": with_dl,
        "without_deadline": counts["no_deadline"],
    }


def weekly_lead_cycle_series(
    timelines: Dict[str, dict],
    days: Sequence[date],
    *,
    max_lead_days: int,
) -> List[dict]:
    by_week_lead: Dict[str, List[float]] = defaultdict(list)
    by_week_cycle: Dict[str, List[float]] = defaultdict(list)
    for tl in timelines.values():
        if not tl.get("task_id") or not tl.get("done_at"):
            continue
        done = tl["done_at"].date()
        iso = done.isocalendar()
        wk = f"{iso.year}-W{iso.week:02d}"
        created = tl.get("created_at")
        in_work = tl.get("in_work_at")
        if created:
            ld = (tl["done_at"] - created).total_seconds() / 86400.0
            if 0 <= ld <= max_lead_days:
                by_week_lead[wk].append(ld)
        if in_work:
            cd = (tl["done_at"] - in_work).total_seconds() / 86400.0
            if 0 <= cd <= max_lead_days:
                by_week_cycle[wk].append(cd)

    weeks: List[str] = []
    if days:
        cur = days[0]
        end = days[-1]
        while cur <= end:
            iso = cur.isocalendar()
            key = f"{iso.year}-W{iso.week:02d}"
            if not weeks or weeks[-1] != key:
                weeks.append(key)
            cur += timedelta(days=7)

    out: List[dict] = []
    for wk in weeks:
        lead = by_week_lead.get(wk) or []
        cycle = by_week_cycle.get(wk) or []
        out.append(
            {
                "week": wk,
                "lead_p50": float(np.percentile(lead, 50)) if lead else None,
                "cycle_p50": float(np.percentile(cycle, 50)) if cycle else None,
                "completions": max(len(lead), len(cycle)),
            }
        )
    return out


def blocked_ratio_snapshot(tasks: Sequence[dict], blocked_column: str) -> dict[str, Any]:
    open_cols = frozenset(KANBAN_COLUMNS[:-1]) if KANBAN_COLUMNS else frozenset()
    open_n = 0
    blocked_n = 0
    for t in tasks:
        if t.get("completed"):
            continue
        col = t.get("column") or ""
        if col not in open_cols:
            continue
        open_n += 1
        if col == blocked_column:
            blocked_n += 1
    ratio = (blocked_n / open_n) if open_n else 0.0
    return {"open": open_n, "blocked": blocked_n, "ratio": round(ratio, 4)}


def goal_mapping_week_insight(
    segment_series: Sequence[dict],
    *,
    window_days: int = 7,
) -> dict[str, Any]:
    if not segment_series:
        return {"dominant": None, "goal_mapped_share": None, "daily_routine_share": None}
    tail = list(segment_series)[-window_days:]
    totals = Counter()
    for row in tail:
        for seg in ALL_SEGMENTS:
            totals[seg] += int(row.get(seg, 0) or 0)
    total = sum(totals.values()) or 1
    shares = {seg: round(totals[seg] / total, 3) for seg in ALL_SEGMENTS}
    dominant = max(ALL_SEGMENTS, key=lambda s: totals[s]) if total else None
    return {
        "dominant": dominant,
        "goal_mapped_share": shares.get(SEGMENT_GOAL_MAPPED),
        "daily_routine_share": shares.get(SEGMENT_DAILY_ROUTINE),
        "unmapped_share": shares.get(SEGMENT_UNMAPPED),
        "totals": dict(totals),
        "window_days": window_days,
    }
