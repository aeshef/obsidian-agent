from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
from datetime import date, datetime
from typing import List, Optional

from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_TODAY_JSON
from planning_bot.services.context_parser import (
    format_for_llm,
    get_snapshots,
    is_valid_mac_snapshot,
    load_chat_snapshot_from_json,
    mac_snapshot_score,
)
from planning_bot.services.reference_date import reference_today
from planning_bot.services.snapshot_query import (
    captured_at_dt,
    filter_by_calendar_range,
    format_snapshot_provenance,
    latest_per_calendar_day,
    parse_date_param,
    parse_range_params,
    resolve_snapshot_for_day,
)


def _load_mac_snaps(*, max_days: int = 14):
    return get_snapshots(CONTEXT_MAC_DIR, days=max_days, logging_window_only=False)


def _parse_mac_ts(value: str, *, end_of_day: bool = False) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    if "T" not in raw and " " not in raw:
        raw = raw[:10]
    try:
        dt = datetime.fromisoformat(raw[:19])
    except ValueError:
        return None
    if "T" not in (value or "").strip() and len((value or "").strip()) <= 10:
        d = dt.date()
        if end_of_day:
            return datetime.combine(d, datetime.max.time()).replace(
                hour=23, minute=59, second=59, microsecond=0
            )
        return datetime.combine(d, datetime.min.time())
    return dt


def resolve_mac_interval(from_ts: str = "", to_ts: str = "") -> tuple[Optional[datetime], Optional[datetime]]:
    """ISO from_ts / to_ts (minute or date). One bound → whole calendar day of that bound."""
    start = _parse_mac_ts(from_ts, end_of_day=False)
    end = _parse_mac_ts(to_ts, end_of_day=True)
    if start and not end and from_ts.strip():
        end = datetime.combine(start.date(), datetime.max.time()).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
    if end and not start and to_ts.strip():
        start = datetime.combine(end.date(), datetime.min.time())
    return start, end


def _snap_dt(snap: dict) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(snap.get("ts", "")))
    except (TypeError, ValueError):
        return None


def filter_mac_snapshots(
    snaps: List[dict],
    *,
    start: datetime,
    end: datetime,
    on_app_change_only: bool = False,
) -> List[dict]:
    out: List[dict] = []
    prev_app: Optional[str] = None
    for s in snaps:
        if not is_valid_mac_snapshot(s):
            continue
        dt = _snap_dt(s)
        if dt is None or dt < start or dt > end:
            continue
        app = s.get("app") or ""
        if on_app_change_only and app == prev_app:
            continue
        prev_app = app
        out.append(s)
    return out


def mac_snapshots_limits() -> tuple[int, int]:
    from shared.agent.platform_config import platform_int

    default_lim = platform_int("planning_mac", "snapshots_limit_default", default=120)
    max_lim = platform_int("planning_mac", "snapshots_limit_max", default=500)
    return max(1, default_lim), max(default_lim, max_lim)


def clamp_mac_snapshots_limit(limit: int) -> int:
    default_lim, max_lim = mac_snapshots_limits()
    if limit == 0:
        return 0
    return max(1, min(int(limit or default_lim), max_lim))


def format_mac_snapshots(
    from_ts: str = "",
    to_ts: str = "",
    *,
    limit: int = 120,
    on_app_change_only: bool = False,
    as_of: Optional[date] = None,
) -> str:
    """Snapshots in [from_ts, to_ts] (~5 min cadence). limit=0 → all in range (cap safety)."""
    start, end = resolve_mac_interval(from_ts, to_ts)
    if start is None or end is None:
        return pdmsg("agent_mac_snapshots_need_range")

    ref = as_of or reference_today()
    span_days = max(3, (ref - start.date()).days + 3, (end.date() - start.date()).days + 3)
    snaps = _load_mac_snaps(max_days=min(120, span_days + 7))
    matched = filter_mac_snapshots(
        snaps, start=start, end=end, on_app_change_only=on_app_change_only
    )
    n_total = len(matched)
    lim = clamp_mac_snapshots_limit(limit)
    if lim > 0 and n_total > lim:
        shown = matched[-lim:]
        truncated = True
    else:
        shown = matched
        truncated = False

    if not shown:
        return pdmsg(
            "agent_mac_snapshots_empty",
            start=start.isoformat(timespec="minutes"),
            end=end.isoformat(timespec="minutes"),
        )

    lines = [
        pdmsg(
            "agent_mac_snapshots_header",
            start=start.isoformat(timespec="minutes"),
            end=end.isoformat(timespec="minutes"),
            shown=len(shown),
            total=n_total,
        ),
        pdmsg("agent_mac_snapshots_columns"),
    ]
    if truncated:
        lines.append(pdmsg("agent_mac_snapshots_truncated", shown=len(shown), total=n_total))
    for s in shown:
        safari = (s.get("safari") or "")[:48]
        lines.append(
            pdmsg(
                "agent_mac_snapshots_row",
                ts=s.get("ts", ""),
                app=s.get("app") or "",
                focus=s.get("focus") or "",
                battery_pct=s.get("battery_pct") if s.get("battery_pct") is not None else "",
                safari=safari,
            )
        )
    return "\n".join(lines)


def format_mac_snapshot(day: str = "", *, as_of: Optional[date] = None) -> str:
    ref = as_of or reference_today()
    target = parse_date_param(day, ref=ref)

    snap = None
    health_day = target
    mac_kw = dict(is_valid=is_valid_mac_snapshot, score_fn=mac_snapshot_score)
    if target is None:
        snap = load_chat_snapshot_from_json(CONTEXT_TODAY_JSON)
        if not snap:
            snaps = _load_mac_snaps(max_days=3)
            snap, health_day = resolve_snapshot_for_day(snaps, None, **mac_kw)
    else:
        snaps = _load_mac_snaps(max_days=max(30, abs((ref - target).days) + 7))
        snap, health_day = resolve_snapshot_for_day(snaps, target, **mac_kw)

    if not snap:
        if target:
            return pdmsg("auto_fd3ee3c714", _p1=target.isoformat())
        return pdmsg("auto_fe57b75eea")

    header = format_snapshot_provenance(
        label=pdmsg("auto_b6eccaacca"),
        health_day=health_day,
        captured_at=captured_at_dt(snap),
        as_of=ref,
        note=pdmsg("auto_dc2316c590"),
    )
    body = format_for_llm(snap)
    return f"{header}\n{body}"


def format_mac_series(from_date: str = "", to_date: str = "") -> str:
    start, end = parse_range_params(from_date, to_date, default_days=30)
    snaps = _load_mac_snaps(max_days=max(30, (end - start).days + 14))
    daily = latest_per_calendar_day(
        filter_by_calendar_range(snaps, start, end),
        is_valid=is_valid_mac_snapshot,
        score_fn=mac_snapshot_score,
    )
    if not daily:
        return pdmsg("auto_40a629d2ad", _p1=start.isoformat(), _p3=end.isoformat())

    lines = [
        pdmsg("agent_mac_series_hint"),
        pdmsg("auto_89cfc4dd5c", _p1=start.isoformat(), _p3=end.isoformat()),
        "date\tapp\tfocus\tbattery_pct",
    ]
    for d in sorted(daily.keys()):
        s = daily[d]
        lines.append(
            f"{d.isoformat()}\t{s.get('app') or ''}\t{s.get('focus') or ''}\t{s.get('battery_pct') or ''}"
        )
    return "\n".join(lines)
