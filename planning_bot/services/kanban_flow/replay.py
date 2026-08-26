"""Action-log replay, ghost close, reliability, and column-history build."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from planning_bot.core.config import BACKLOG_COLUMN, DONE_COLUMN, KANBAN_COLUMNS
from planning_bot.services.kanban_flow.history import (
    _iter_days,
    _load_json_history,
    _snapshot_from_board_state,
    build_column_snapshot,
    calibrate_history_with_trusted_totals,
    fill_trusted_totals_gaps,
    save_json_history,
    trim_history,
    upsert_today_snapshot,
)
from planning_bot.services.kanban_flow.window import _flow_cfg
from shared.agent.platform_config import platform_int
from shared.goals.task_segment import flow_daily_categories


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
        return 100.0 * int(row["id"]) / max(1, int(row["all"]))

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
