"""Column-history persistence: save, trim, calibrate, fill, snapshot, upsert."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Sequence, Tuple

from planning_bot.core.config import DONE_COLUMN
from shared.goals.task_segment import ALL_SEGMENTS, classify_task_goal_segment


def _iter_days(d0: date, d1: date) -> List[date]:
    out: List[date] = []
    cur = d0
    while cur <= d1:
        out.append(cur)
        cur += timedelta(days=1)
    return out


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
