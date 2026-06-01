from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from planning_bot.services.iphone_health_fields import health_snapshot_score, is_valid_health_snapshot

SnapshotPredicate = Callable[[Mapping[str, Any]], bool]
SnapshotScoreFn = Callable[[Mapping[str, Any]], int]
from planning_bot.services.reference_date import reference_today


def snap_calendar_day(snap: Dict[str, Any]) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(snap.get("ts", ""))).date()
    except (TypeError, ValueError):
        return None


def parse_date_param(value: str, *, ref: Optional[date] = None) -> Optional[date]:
    'Operation implementation.'
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return ref or reference_today()


def parse_range_params(
    from_date: str,
    to_date: str,
    *,
    default_days: int = 7,
    ref: Optional[date] = None,
) -> tuple[date, date]:
    'Operation implementation.'
    today = ref or reference_today()
    end = parse_date_param(to_date, ref=today) or today
    start = parse_date_param(from_date, ref=today)
    if start is None:
        start = end - timedelta(days=max(1, default_days) - 1)
    if start > end:
        start, end = end, start
    return start, end


def filter_by_calendar_range(
    snaps: Sequence[Dict[str, Any]],
    start: date,
    end: date,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in snaps:
        d = snap_calendar_day(s)
        if d is not None and start <= d <= end:
            out.append(s)
    return out


def _pick_richer_snapshot(
    current: Dict[str, Any] | None,
    candidate: Dict[str, Any],
    *,
    score_fn: SnapshotScoreFn = health_snapshot_score,
) -> Dict[str, Any]:
    if current is None:
        return candidate
    q_cur = score_fn(current)
    q_new = score_fn(candidate)
    if q_new > q_cur:
        return candidate
    if q_new < q_cur:
        return current
    return candidate if str(candidate.get("ts", "")) >= str(current.get("ts", "")) else current


def latest_per_calendar_day(
    snaps: Sequence[Dict[str, Any]],
    *,
    is_valid: SnapshotPredicate | None = None,
    score_fn: SnapshotScoreFn | None = None,
) -> Dict[date, Dict[str, Any]]:
    'Operation implementation.'
    valid_fn = is_valid or is_valid_health_snapshot
    score = score_fn or health_snapshot_score
    by_day: Dict[date, Dict[str, Any]] = {}
    for s in snaps:
        if not valid_fn(s):
            continue
        d = snap_calendar_day(s)
        if d is not None:
            by_day[d] = _pick_richer_snapshot(by_day.get(d), s, score_fn=score)
    return by_day


def snapshot_on_day(
    snaps: Sequence[Dict[str, Any]],
    day: date,
    *,
    is_valid: SnapshotPredicate | None = None,
    score_fn: SnapshotScoreFn | None = None,
) -> Optional[Dict[str, Any]]:
    return latest_per_calendar_day(
        [s for s in snaps if snap_calendar_day(s) == day],
        is_valid=is_valid,
        score_fn=score_fn,
    ).get(day)


def latest_snapshot(
    snaps: Sequence[Dict[str, Any]],
    *,
    is_valid: SnapshotPredicate | None = None,
    score_fn: SnapshotScoreFn | None = None,
) -> Optional[Dict[str, Any]]:
    valid_fn = is_valid or is_valid_health_snapshot
    score = score_fn or health_snapshot_score
    valid = [s for s in snaps if valid_fn(s)]
    if not valid:
        return None
    best: Dict[str, Any] | None = None
    for s in valid:
        best = _pick_richer_snapshot(best, s, score_fn=score)
    return best


def resolve_snapshot_for_day(
    snaps: Sequence[Dict[str, Any]],
    day: Optional[date],
    *,
    is_valid: SnapshotPredicate | None = None,
    score_fn: SnapshotScoreFn | None = None,
) -> tuple[Optional[Dict[str, Any]], Optional[date]]:
    'Operation implementation.'
    if not snaps:
        return None, None
    if day is None:
        snap = latest_snapshot(snaps, is_valid=is_valid, score_fn=score_fn)
        return snap, snap_calendar_day(snap) if snap else None
    snap = snapshot_on_day(snaps, day, is_valid=is_valid, score_fn=score_fn)
    return snap, day if snap else None


def format_snapshot_provenance(
    *,
    label: str,
    health_day: Optional[date],
    captured_at: Optional[datetime],
    as_of: Optional[date] = None,
    note: str = "",
) -> str:
    'Operation implementation.'
    as_of = as_of or reference_today()
    lines = [label]
    if health_day:
        lines.append(pdmsg("auto_ae400127c8", _p1=health_day.isoformat()))
    if captured_at:
        lines.append(f"  captured_at: {captured_at.isoformat(timespec='minutes')}")
    lines.append(f"  as_of_today: {as_of.isoformat()}")
    if note:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def captured_at_dt(snap: Dict[str, Any]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(snap.get("ts", "")))
    except (TypeError, ValueError):
        return None


def pick_fields(
    snap: Dict[str, Any],
    fields: Optional[Iterable[str]],
    *,
    allowed: Optional[set[str]] = None,
) -> Dict[str, Any]:
    if not fields:
        keys = sorted(k for k in snap if k not in ("ts", "source") and snap[k] not in (None, ""))
        if allowed:
            keys = [k for k in keys if k in allowed]
        return {k: snap[k] for k in keys}
    out: Dict[str, Any] = {}
    for k in fields:
        k = k.strip()
        if not k:
            continue
        if k in snap and snap[k] not in (None, ""):
            out[k] = snap[k]
    return out
