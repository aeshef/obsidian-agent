"""Task timelines, lead/cycle stats, flow series, aging, transitions."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, FrozenSet, List, Optional, Sequence

import numpy as np

from planning_bot.core.config import KANBAN_COLUMNS
from planning_bot.services.action_log_parser import get_completion_events
from shared.goals.task_segment import ALL_SEGMENTS, classify_task_goal_segment


def _task_key(data: dict) -> str:
    tid = (data.get("task_id") or "").strip().lower()
    if tid:
        return f"id:{tid}"
    title = (data.get("title") or "").strip()
    return f"title:{title}" if title else ""


def build_task_timelines(
    events: Sequence[dict],
    *,
    in_work_column: str,
    done_column: str,
) -> Dict[str, dict]:
    timelines: Dict[str, dict] = {}
    for e in events:
        data = e.get("data") or {}
        key = _task_key(data)
        if not key:
            continue
        tl = timelines.setdefault(
            key,
            {
                "task_id": (data.get("task_id") or "").strip().lower(),
                "title": (data.get("title") or "").strip(),
                "category": (data.get("category") or "").strip(),
                "created_at": None,
                "in_work_at": None,
                "done_at": None,
            },
        )
        ts = e["dt"]
        et = e.get("type")
        if et == "task_created" and tl["created_at"] is None:
            tl["created_at"] = ts
            if data.get("category"):
                tl["category"] = data["category"]
        elif et == "task_moved":
            to_col = data.get("to") or ""
            if to_col == in_work_column and tl["in_work_at"] is None:
                tl["in_work_at"] = ts
            if to_col == done_column and tl["done_at"] is None:
                tl["done_at"] = ts
        elif et == "task_completed" and tl["done_at"] is None:
            tl["done_at"] = ts
    return timelines


def _percentiles(days: List[float]) -> dict[str, Optional[float]]:
    if not days:
        return {"p50": None, "p85": None, "p95": None, "n": 0}
    arr = np.asarray(days, dtype=float)
    return {
        "p50": float(np.percentile(arr, 50)),
        "p85": float(np.percentile(arr, 85)),
        "p95": float(np.percentile(arr, 95)),
        "n": int(len(arr)),
    }


def compute_lead_cycle_stats(
    timelines: Dict[str, dict],
    *,
    max_lead_days: int,
) -> dict[str, Any]:
    lead_days: List[float] = []
    cycle_days: List[float] = []
    with_id = 0
    for tl in timelines.values():
        if not tl.get("task_id"):
            continue
        done = tl.get("done_at")
        if not done:
            continue
        with_id += 1
        created = tl.get("created_at")
        in_work = tl.get("in_work_at")
        if created:
            ld = (done - created).total_seconds() / 86400.0
            if 0 <= ld <= max_lead_days:
                lead_days.append(ld)
        if in_work:
            cd = (done - in_work).total_seconds() / 86400.0
            if 0 <= cd <= max_lead_days:
                cycle_days.append(cd)
    return {
        "lead_time_days": _percentiles(lead_days),
        "cycle_time_days": _percentiles(cycle_days),
        "completed_with_task_id": with_id,
    }


def daily_flow_series(
    events: Sequence[dict],
    days: Sequence[date],
) -> List[dict]:
    arrivals: Counter[date] = Counter()
    departures: Counter[date] = Counter()
    for e in events:
        d = e["dt"].date()
        if e.get("type") == "task_created":
            arrivals[d] += 1
    completions = get_completion_events(list(events))
    for e in completions:
        departures[e["dt"].date()] += 1

    debt = 0
    series: List[dict] = []
    for d in days:
        arr = int(arrivals.get(d, 0))
        dep = int(departures.get(d, 0))
        debt += arr - dep
        series.append(
            {
                "date": d.isoformat(),
                "arrivals": arr,
                "departures": dep,
                "flow_debt": debt,
            }
        )
    return series


def weekly_throughput_series(
    events: Sequence[dict],
    days: Sequence[date],
) -> List[dict]:
    completions = get_completion_events(list(events))
    by_week: Counter[str] = Counter()
    for e in completions:
        iso = e["dt"].date().isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        by_week[key] += 1
    if not days:
        return []
    weeks_seen: List[str] = []
    cur = days[0]
    end = days[-1]
    while cur <= end:
        iso = cur.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        if not weeks_seen or weeks_seen[-1] != key:
            weeks_seen.append(key)
        cur += timedelta(days=7)
    return [{"week": w, "throughput": int(by_week.get(w, 0))} for w in weeks_seen]


def completions_by_segment_series(
    events: Sequence[dict],
    days: Sequence[date],
    *,
    mapping: Dict[str, List[str]],
    daily_categories: FrozenSet[str],
    cat_by_id: Dict[str, str],
    cat_by_title: Dict[str, str],
) -> List[dict]:
    completions = get_completion_events(list(events))
    by_day_seg: Dict[date, Counter[str]] = defaultdict(Counter)

    def _cat(data: dict) -> str:
        c = (data.get("category") or "").strip()
        if c:
            return c
        tid = (data.get("task_id") or "").strip().lower()
        if tid and tid in cat_by_id:
            return cat_by_id[tid]
        title = (data.get("title") or "").strip()
        return cat_by_title.get(title, "")

    for e in completions:
        d = e["dt"].date()
        data = e.get("data") or {}
        seg = classify_task_goal_segment(
            data.get("task_id"),
            _cat(data),
            mapping,
            daily_categories,
        )
        by_day_seg[d][seg] += 1

    return [
        {
            "date": d.isoformat(),
            **{seg: int(by_day_seg[d].get(seg, 0)) for seg in ALL_SEGMENTS},
        }
        for d in days
    ]


def transition_matrix(events: Sequence[dict]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for e in events:
        if e.get("type") != "task_moved":
            continue
        data = e.get("data") or {}
        fr = (data.get("from") or "").strip()
        to = (data.get("to") or "").strip()
        if not fr or not to:
            continue
        counts[f"{fr}\t{to}"] += 1
    return dict(counts)


def _strip_col_label(name: str) -> str:
    import re

    s = re.sub(
        "[" f"{chr(0x1F300)}-{chr(0x1FAFF)}" f"{chr(0x2600)}-{chr(0x27BF)}" "]+",
        "",
        name or "",
        flags=re.UNICODE,
    ).strip()
    return s or (name or "").strip() or "?"


def aging_open_tasks(
    tasks: Sequence[dict],
    *,
    today: date,
    stale_days: int,
) -> dict[str, Any]:
    buckets = {"0_7": 0, "8_14": 0, "15_30": 0, "31_plus": 0}
    stale: List[dict] = []
    open_columns = frozenset(KANBAN_COLUMNS[:-1]) if KANBAN_COLUMNS else frozenset()

    for t in tasks:
        if t.get("completed"):
            continue
        col = t.get("column") or ""
        if col not in open_columns:
            continue
        created_s = (t.get("created_date") or "").strip()
        age = None
        if created_s:
            try:
                created = datetime.strptime(created_s[:10], "%Y-%m-%d").date()
                age = (today - created).days
            except ValueError:
                age = None
        if age is None:
            buckets["31_plus"] += 1
            continue
        if age <= 7:
            buckets["0_7"] += 1
        elif age <= 14:
            buckets["8_14"] += 1
        elif age <= 30:
            buckets["15_30"] += 1
        else:
            buckets["31_plus"] += 1
        if age >= stale_days:
            stale.append(
                {
                    "task_id": t.get("task_id") or "",
                    "title": (t.get("title") or "")[:80],
                    "column": col,
                    "age_days": age,
                    "category": t.get("category") or "",
                }
            )
    stale.sort(key=lambda x: (-int(x.get("age_days") or 0), x.get("title") or ""))

    # Cemetery matrices: category/column × age bucket
    age_keys = ("0_7", "8_14", "15_30", "31_plus")
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {k: 0 for k in age_keys})
    by_col: dict[str, dict[str, int]] = defaultdict(lambda: {k: 0 for k in age_keys})
    for t in tasks:
        if t.get("completed"):
            continue
        col = t.get("column") or ""
        if col not in open_columns:
            continue
        created_s = (t.get("created_date") or "").strip()
        age = None
        if created_s:
            try:
                created = datetime.strptime(created_s[:10], "%Y-%m-%d").date()
                age = (today - created).days
            except ValueError:
                age = None
        if age is None:
            bucket = "31_plus"
        elif age <= 7:
            bucket = "0_7"
        elif age <= 14:
            bucket = "8_14"
        elif age <= 30:
            bucket = "15_30"
        else:
            bucket = "31_plus"
        cat = (t.get("category") or "").strip() or "_"
        by_cat[cat][bucket] += 1
        by_col[_strip_col_label(col)][bucket] += 1

    return {
        "buckets": buckets,
        "stale_tasks": stale[:40],
        "stale_count": len(stale),
        "by_category": dict(by_cat),
        "by_column": dict(by_col),
    }
