"""Kanban flow metrics from action logs, board snapshots, and goals mapping."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from planning_bot.core.config import BACKLOG_COLUMN, DONE_COLUMN, IN_WORK_COLUMN, KANBAN_COLUMNS
from planning_bot.services.action_log_parser import (
    collect_events_from_logs,
    get_completion_events,
    is_completion_event,
)
from shared.agent.platform_config import platform_int
from shared.goals.task_segment import (
    ALL_SEGMENTS,
    SEGMENT_DAILY_ROUTINE,
    SEGMENT_GOAL_MAPPED,
    SEGMENT_UNMAPPED,
    classify_task_goal_segment,
    flow_daily_categories,
)


def _flow_cfg() -> dict[str, int]:
    return {
        "rolling_window_days": max(
            1, platform_int("planning_kanban_flow", "rolling_window_days", default=7)
        ),
        "history_max_days": max(
            30, platform_int("planning_kanban_flow", "history_max_days", default=365)
        ),
        "aging_stale_days": max(
            1, platform_int("planning_kanban_flow", "aging_stale_days", default=14)
        ),
        "lead_time_max_days": max(
            7, platform_int("planning_kanban_flow", "lead_time_max_days", default=180)
        ),
        "replay_min_task_id_coverage_pct": max(
            1,
            min(
                100,
                platform_int(
                    "planning_kanban_flow",
                    "replay_min_task_id_coverage_pct",
                    default=95,
                ),
            ),
        ),
        "replay_min_events_per_month": max(
            20,
            platform_int(
                "planning_kanban_flow", "replay_min_events_per_month", default=200
            ),
        ),
        "trusted_interpolate_max_gap_days": max(
            1,
            platform_int(
                "planning_kanban_flow",
                "trusted_interpolate_max_gap_days",
                default=2,
            ),
        ),
    }


def _iter_days(d0: date, d1: date) -> List[date]:
    out: List[date] = []
    cur = d0
    while cur <= d1:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _task_key(data: dict) -> str:
    tid = (data.get("task_id") or "").strip().lower()
    if tid:
        return f"id:{tid}"
    title = (data.get("title") or "").strip()
    return f"title:{title}" if title else ""


def _load_json_history(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    snaps = raw.get("snapshots") if isinstance(raw, dict) else raw
    return list(snaps) if isinstance(snaps, list) else []


def save_json_history(path: Path, snapshots: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {"version": 1, "snapshots": list(snapshots)}
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def trim_history(snapshots: Sequence[dict], *, max_days: int) -> List[dict]:
    if not snapshots:
        return []
    cutoff = date.today() - timedelta(days=max(1, max_days))
    out = [s for s in snapshots if str(s.get("date", "")) >= cutoff.isoformat()]
    out.sort(key=lambda s: str(s.get("date", "")))
    return out


def _scaled_counts(
    counts: Dict[str, Any],
    *,
    target_total: int,
) -> Dict[str, int]:
    keys = list(counts.keys())
    if not keys:
        return {}
    base = [max(0, int(counts.get(k, 0) or 0)) for k in keys]
    cur_total = sum(base)
    if cur_total <= 0:
        return {k: 0 for k in keys}
    if target_total <= 0:
        return {k: 0 for k in keys}
    raw = [v * float(target_total) / float(cur_total) for v in base]
    flo = [int(x) for x in raw]
    rem = target_total - sum(flo)
    frac_idx = sorted(
        range(len(keys)),
        key=lambda i: (raw[i] - flo[i], base[i]),
        reverse=True,
    )
    for i in frac_idx[: max(0, rem)]:
        flo[i] += 1
    return {k: flo[i] for i, k in enumerate(keys)}


def calibrate_history_with_trusted_totals(
    history: Sequence[dict],
    trusted_open_totals: Dict[str, int],
) -> Tuple[List[dict], int]:
    if not history or not trusted_open_totals:
        return list(history), 0
    out: List[dict] = []
    calibrated_days = 0
    for snap in history:
        d = str(snap.get("date", ""))
        # Never distort a live board snapshot — it is ground truth for column ratios.
        if str(snap.get("source", "")) == "board":
            out.append(dict(snap))
            continue
        if d not in trusted_open_totals:
            out.append(dict(snap))
            continue
        trusted_total = max(0, int(trusted_open_totals[d]))
        by_col = _scaled_counts(
            dict(snap.get("by_column") or {}),
            target_total=trusted_total,
        )
        by_seg = _scaled_counts(
            dict(snap.get("by_goal_segment") or {}),
            target_total=trusted_total,
        )
        ns = dict(snap)
        ns["total_open"] = trusted_total
        ns["by_column"] = by_col
        ns["by_goal_segment"] = by_seg
        src = str(ns.get("source", "replay"))
        if src == "replay":
            ns["source"] = "replay_calibrated"
        calibrated_days += 1
        out.append(ns)
    return out, calibrated_days


def fill_trusted_totals_gaps(
    dates: Sequence[str],
    trusted_open_totals: Dict[str, int],
    *,
    max_gap_days: int,
) -> Dict[str, int]:
    """Interpolate isolated missing days between trusted anchors."""
    out = dict(trusted_open_totals)
    if not dates:
        return out
    known = sorted([d for d in dates if d in trusted_open_totals])
    if len(known) < 2:
        return out
    for i in range(len(known) - 1):
        left_s = known[i]
        right_s = known[i + 1]
        left = datetime.strptime(left_s, "%Y-%m-%d").date()
        right = datetime.strptime(right_s, "%Y-%m-%d").date()
        gap = (right - left).days - 1
        if gap <= 0 or gap > max_gap_days:
            continue
        lv = int(trusted_open_totals[left_s])
        rv = int(trusted_open_totals[right_s])
        for step in range(1, gap + 1):
            d = left + timedelta(days=step)
            ds = d.isoformat()
            if ds in out:
                continue
            interp = round(lv + (rv - lv) * (step / float(gap + 1)))
            out[ds] = int(max(0, interp))
    return out


def build_column_snapshot(
    tasks: Sequence[dict],
    *,
    mapping: Dict[str, List[str]],
    daily_categories: FrozenSet[str],
    open_columns: FrozenSet[str],
) -> dict[str, Any]:
    by_column: Counter[str] = Counter()
    by_segment: Counter[str] = Counter()
    skipped = 0
    for t in tasks:
        if t.get("completed"):
            continue
        col = t.get("column") or ""
        if col not in open_columns and col != DONE_COLUMN:
            if col:
                skipped += 1
            continue
        if col == DONE_COLUMN:
            continue
        by_column[col] += 1
        seg = classify_task_goal_segment(
            t.get("task_id"),
            t.get("category"),
            mapping,
            daily_categories,
        )
        by_segment[seg] += 1
    total_open = int(sum(by_column.values()))
    today_s = date.today().isoformat()
    return {
        "date": today_s,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_open": total_open,
        "by_column": dict(by_column),
        "by_goal_segment": {k: int(by_segment.get(k, 0)) for k in ALL_SEGMENTS},
        "skipped_unknown_column": skipped,
    }


def upsert_today_snapshot(history: List[dict], snap: dict) -> List[dict]:
    today_s = snap.get("date") or date.today().isoformat()
    rest = [s for s in history if s.get("date") != today_s]
    rest.append(snap)
    rest.sort(key=lambda s: str(s.get("date", "")))
    return rest


def _snapshot_from_board_state(
    board: Dict[str, dict],
    *,
    day: date,
    mapping: Dict[str, List[str]],
    daily_categories: FrozenSet[str],
    open_columns: FrozenSet[str],
    source: str,
) -> dict[str, Any]:
    by_column: Counter[str] = Counter()
    by_segment: Counter[str] = Counter()
    for tid, st in board.items():
        if not st.get("open"):
            continue
        col = st.get("column") or ""
        if col not in open_columns:
            continue
        by_column[col] += 1
        seg = classify_task_goal_segment(
            tid,
            st.get("category") or "",
            mapping,
            daily_categories,
        )
        by_segment[seg] += 1
    return {
        "date": day.isoformat(),
        "updated_at": f"{day.isoformat()} 23:59",
        "total_open": int(sum(by_column.values())),
        "by_column": dict(by_column),
        "by_goal_segment": {k: int(by_segment.get(k, 0)) for k in ALL_SEGMENTS},
        "source": source,
    }


def _is_terminal_column(col: str, done_column: str) -> bool:
    """Done / archive / similar — task leaves open WIP."""
    c = (col or "").strip()
    if not c:
        return False
    if done_column and c == done_column:
        return True
    low = c.casefold()
    if "archive" in low:
        return True
    # Locale archive label (YAML) — e.g. RU short form used in column titles.
    try:
        from planning_bot.core.pdmsg import pdmsg

        marker = (pdmsg("goals_mapping_review_source_archive") or "").strip().casefold()
    except Exception:
        marker = ""
    return bool(marker) and marker in low


def _replay_apply_event(
    board: Dict[str, dict],
    e: dict,
    *,
    backlog_column: str,
    done_column: str,
    cat_by_id: Dict[str, str],
    cat_by_title: Dict[str, str],
) -> None:
    data = e.get("data") or {}
    tid = (data.get("task_id") or "").strip().lower()
    if not tid:
        return

    def _cat() -> str:
        c = (data.get("category") or "").strip()
        if c:
            return c
        if tid in cat_by_id:
            return cat_by_id[tid]
        title = (data.get("title") or "").strip()
        if title and title in cat_by_title:
            return cat_by_title[title]
        return (board.get(tid) or {}).get("category") or ""

    et = e.get("type")
    if et == "task_created":
        board[tid] = {"column": backlog_column, "category": _cat(), "open": True}
        return
    if et == "task_moved":
        fr = (data.get("from") or "").strip()
        to = (data.get("to") or "").strip()
        if tid not in board:
            board[tid] = {
                "column": fr or backlog_column,
                "category": _cat(),
                "open": True,
            }
        st = board[tid]
        cat = _cat()
        if cat:
            st["category"] = cat
        if _is_terminal_column(to, done_column):
            st["column"] = to or done_column
            st["open"] = False
        elif to:
            st["column"] = to
            st["open"] = True
        return
    if et == "task_completed":
        if tid not in board:
            board[tid] = {"column": done_column, "category": _cat(), "open": False}
        else:
            board[tid]["open"] = False


def infer_ghost_close_dates(
    events: Sequence[dict],
    *,
    live_open_ids: FrozenSet[str],
    backlog_column: str,
    done_column: str,
    cat_by_id: Dict[str, str],
    cat_by_title: Dict[str, str],
) -> Dict[str, date]:
    """
    Tasks still 'open' after full replay but absent from the live board are ghosts
    (completed/archived/deleted without a logged completion). Close them on the day
    of their last event so CFD ratios are not permanently backlog-skewed.
    """
    board: Dict[str, dict] = {}
    last_day: Dict[str, date] = {}
    for e in sorted(
        [x for x in events if (x.get("data") or {}).get("task_id")],
        key=lambda x: x["dt"],
    ):
        tid = ((e.get("data") or {}).get("task_id") or "").strip().lower()
        if not tid:
            continue
        _replay_apply_event(
            board,
            e,
            backlog_column=backlog_column,
            done_column=done_column,
            cat_by_id=cat_by_id,
            cat_by_title=cat_by_title,
        )
        dt = e.get("dt")
        if dt is not None:
            last_day[tid] = dt.date() if hasattr(dt, "date") else dt
    closes: Dict[str, date] = {}
    for tid, st in board.items():
        if not st.get("open"):
            continue
        if tid in live_open_ids:
            continue
        if tid in last_day:
            closes[tid] = last_day[tid]
    return closes


def replay_column_snapshots_from_events(
    events: Sequence[dict],
    *,
    mapping: Dict[str, List[str]],
    daily_categories: FrozenSet[str],
    open_columns: FrozenSet[str],
    cat_by_id: Dict[str, str],
    cat_by_title: Dict[str, str],
    start_day: date,
    end_day: date,
    live_today_snap: Optional[dict] = None,
    backlog_column: str = BACKLOG_COLUMN,
    done_column: str = DONE_COLUMN,
    live_open_ids: Optional[FrozenSet[str]] = None,
) -> List[dict]:
    """Reconstruct end-of-day WIP by column/segment from action-log replay."""
    stable = sorted(
        [e for e in events if (e.get("data") or {}).get("task_id")],
        key=lambda x: x["dt"],
    )
    if not stable:
        return []

    ghost_close = (
        infer_ghost_close_dates(
            stable,
            live_open_ids=live_open_ids or frozenset(),
            backlog_column=backlog_column,
            done_column=done_column,
            cat_by_id=cat_by_id,
            cat_by_title=cat_by_title,
        )
        if live_open_ids is not None
        else {}
    )

    board: Dict[str, dict] = {}
    snapshots: List[dict] = []
    idx = 0
    n = len(stable)
    today_s = end_day.isoformat()

    for d in _iter_days(start_day, end_day):
        end_dt = datetime.combine(d, datetime.max.time())
        while idx < n and stable[idx]["dt"] <= end_dt:
            _replay_apply_event(
                board,
                stable[idx],
                backlog_column=backlog_column,
                done_column=done_column,
                cat_by_id=cat_by_id,
                cat_by_title=cat_by_title,
            )
            idx += 1
        if ghost_close:
            for tid, close_d in ghost_close.items():
                # Keep open through the last-event day; drop from the next morning.
                if d > close_d and tid in board and board[tid].get("open"):
                    board[tid]["open"] = False
        if d.isoformat() == today_s and live_today_snap:
            snap = dict(live_today_snap)
            snap["source"] = "board"
            snapshots.append(snap)
        else:
            snapshots.append(
                _snapshot_from_board_state(
                    board,
                    day=d,
                    mapping=mapping,
                    daily_categories=daily_categories,
                    open_columns=open_columns,
                    source="replay",
                )
            )
    return snapshots


def should_auto_backfill_column_history(existing_days: int) -> bool:
    threshold = platform_int(
        "planning_kanban_flow", "auto_backfill_min_history_days", default=7
    )
    return existing_days < max(1, threshold)


def infer_reliable_start_day(events: Sequence[dict], cfg: dict[str, int]) -> Optional[date]:
    """Pick earliest month where task_id coverage is reliable and stays reliable."""
    if not events:
        return None
    by_month: Dict[str, dict[str, Any]] = {}
    for e in events:
        dt = e.get("dt")
        if dt is None:
            continue
        key = dt.strftime("%Y-%m")
        row = by_month.setdefault(key, {"all": 0, "id": 0})
        row["all"] += 1
        if (e.get("data") or {}).get("task_id"):
            row["id"] += 1
    if not by_month:
        return None

    months = sorted(by_month.keys())
    cov_need = int(cfg["replay_min_task_id_coverage_pct"])
    events_need = int(cfg["replay_min_events_per_month"])

    def _cov(m: str) -> float:
        row = by_month[m]
        return (100.0 * int(row["id"]) / max(1, int(row["all"])))

    for i, month in enumerate(months):
        row = by_month[month]
        if int(row["all"]) < events_need or _cov(month) < cov_need:
            continue
        tail_ok = True
        for m in months[i:]:
            row2 = by_month[m]
            # allow sparse current month, enforce reliability on dense months
            if int(row2["all"]) < events_need:
                continue
            if _cov(m) < cov_need:
                tail_ok = False
                break
        if tail_ok:
            return datetime.strptime(month + "-01", "%Y-%m-%d").date()
    return None


def build_column_history(
    *,
    events: Sequence[dict],
    column_history_path: Path,
    kanban_schema: dict,
    mapping: Dict[str, List[str]],
    board_tasks: Sequence[dict],
    cat_by_id: Dict[str, str],
    cat_by_title: Dict[str, str],
    backfill_columns: bool = False,
    allow_auto_backfill: bool = True,
    trusted_open_totals: Optional[Dict[str, int]] = None,
) -> Tuple[List[dict], dict[str, Any]]:
    """Persist daily column snapshots; optionally backfill from action-log replay."""
    cfg = _flow_cfg()
    daily_cats = flow_daily_categories(kanban_schema)
    open_columns = frozenset(KANBAN_COLUMNS[:-1]) if KANBAN_COLUMNS else frozenset()

    live_snap = build_column_snapshot(
        board_tasks,
        mapping=mapping,
        daily_categories=daily_cats,
        open_columns=open_columns,
    )
    live_open_ids = frozenset(
        (t.get("task_id") or "").strip().lower()
        for t in board_tasks
        if (t.get("task_id") or "").strip()
        and not t.get("completed")
        and (t.get("column") or "") in open_columns
    )
    existing = trim_history(
        _load_json_history(column_history_path), max_days=cfg["history_max_days"]
    )
    meta: dict[str, Any] = {"mode": "incremental", "days": len(existing)}

    stable = [e for e in events if (e.get("data") or {}).get("task_id")]
    do_backfill = backfill_columns or (
        allow_auto_backfill
        and stable
        and should_auto_backfill_column_history(len(existing))
    )

    if do_backfill and stable:
        start_day = min(e["dt"].date() for e in stable)
        reliable_start = infer_reliable_start_day(events, cfg)
        if reliable_start and reliable_start > start_day:
            start_day = reliable_start
        end_day = date.today()
        history = replay_column_snapshots_from_events(
            events,
            mapping=mapping,
            daily_categories=daily_cats,
            open_columns=open_columns,
            cat_by_id=cat_by_id,
            cat_by_title=cat_by_title,
            start_day=start_day,
            end_day=end_day,
            live_today_snap=live_snap,
            live_open_ids=live_open_ids,
        )
        history = trim_history(history, max_days=cfg["history_max_days"])
        meta = {
            "mode": "backfill",
            "days": len(history),
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "reliable_start": reliable_start.isoformat() if reliable_start else None,
            "ghosts_closed": len(
                infer_ghost_close_dates(
                    stable,
                    live_open_ids=live_open_ids,
                    backlog_column=BACKLOG_COLUMN,
                    done_column=DONE_COLUMN,
                    cat_by_id=cat_by_id,
                    cat_by_title=cat_by_title,
                )
            ),
        }
    else:
        history = upsert_today_snapshot(existing, live_snap)
        meta["mode"] = "incremental"

    dates = [str(s.get("date", "")) for s in history if s.get("date")]
    trusted_full = fill_trusted_totals_gaps(
        dates,
        trusted_open_totals or {},
        max_gap_days=cfg["trusted_interpolate_max_gap_days"],
    )
    history, calibrated_days = calibrate_history_with_trusted_totals(
        history,
        trusted_full,
    )
    if calibrated_days:
        meta["calibrated_days"] = calibrated_days

    save_json_history(column_history_path, history)
    meta["path"] = str(column_history_path)
    return history, meta


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
    return {"buckets": buckets, "stale_tasks": stale[:40], "stale_count": len(stale)}


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
    snap = next((s for s in reversed(history) if s.get("date") == date.today().isoformat()), history[-1] if history else {})

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


def format_kanban_flow_for_agent(metrics: dict[str, Any], msg: Any) -> str:
    if metrics.get("status") == "no_task_id_events":
        return msg("kanban_flow_agent_no_data")
    s = metrics.get("summary") or {}
    ins = metrics.get("goal_mapping_insight") or {}
    lines = [
        msg("kanban_flow_agent_header", period_end=(metrics.get("period") or {}).get("end", "?")),
        msg(
            "kanban_flow_agent_summary",
            open_tasks=s.get("current_open", 0),
            completions=s.get("total_completions", 0),
            flow_debt=s.get("flow_debt_today", 0),
            lead_p50=s.get("lead_time_p50_days"),
            cycle_p50=s.get("cycle_time_p50_days"),
            blocked_pct=round(100 * float(s.get("blocked_ratio") or 0), 1),
            stale=s.get("stale_open_count", 0),
        ),
        msg(
            "kanban_flow_agent_goal_segment",
            dominant=ins.get("dominant") or "?",
            goal_share=ins.get("goal_mapped_share"),
            daily_share=ins.get("daily_routine_share"),
            unmapped_share=ins.get("unmapped_share"),
        ),
    ]
    cov = metrics.get("coverage") or {}
    lines.append(
        msg(
            "kanban_flow_agent_coverage",
            pct=cov.get("task_id_coverage_pct", 0),
        )
    )
    return "\n".join(lines)
