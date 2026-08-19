from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


from planning_bot.services.iphone_health_fields import (
    META_KEYS,
    discover_numeric_keys,
    is_valid_health_snapshot,
    string_keys,
    extract_raw_fields,
    normalize_raw_fields,
    parse_ts as _parse_health_ts,
)


def _parse_ts(s: str) -> Optional[datetime]:
    from planning_bot.services.iphone_health_fields import file_ts_formats

    return _parse_health_ts(s, formats=file_ts_formats())


def parse_iphone_file(path: Path) -> Optional[Dict[str, Any]]:
    'Operation implementation.'
    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None

    from planning_bot.services.iphone_snapshot_names import parse_filename_ts

    fn_ts: Optional[datetime] = parse_filename_ts(path.name)
    raw = extract_raw_fields(text)
    snap = normalize_raw_fields(raw, fallback_ts=fn_ts)
    if snap is None:
        return None
    # (comment)
    ts = _parse_ts(str(snap.get("ts", ""))) or fn_ts
    if ts:
        snap["ts"] = ts.isoformat(timespec="minutes")
    return snap


def get_snapshots(
    iphone_dir: Path,
    days: int | None = 30,
) -> List[Dict[str, Any]]:
    'Operation implementation.'
    if not iphone_dir.exists():
        return []
    cutoff: datetime | None = None
    if days is not None:
        cutoff = datetime.now() - timedelta(days=days)
    snaps: List[Dict[str, Any]] = []
    for path in iphone_dir.glob("*.txt"):
        if path.name.startswith(".") or " copy" in path.name.lower():
            continue
        snap = parse_iphone_file(path)
        if snap is None or not is_valid_health_snapshot(snap):
            continue
        try:
            dt = datetime.fromisoformat(str(snap.get("ts", "")))
        except (KeyError, ValueError, TypeError):
            continue
        if cutoff is not None:
            from shared.query.ts import dt_ge

            if not dt_ge(dt, cutoff):
                continue
        snaps.append(snap)
    snaps.sort(key=lambda x: x.get("ts", ""))
    return snaps


def get_latest_snapshot(iphone_dir: Path) -> Optional[Dict[str, Any]]:
    snaps = get_snapshots(iphone_dir, days=3)
    return snaps[-1] if snaps else None


def get_week_snapshots(iphone_dir: Path) -> List[Dict[str, Any]]:
    return get_snapshots(iphone_dir, days=7)


def week_numeric_aggregates(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    'Operation implementation.'
    out: Dict[str, Any] = {"snapshot_count": len(snaps)}
    for field in discover_numeric_keys(snaps):
        vals: List[float] = []
        for s in snaps:
            v = s.get(field)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if not vals:
            continue
        out[field] = {
            "count": len(vals),
            "avg": round(sum(vals) / len(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
        }
    return out


def format_for_llm(snap: Optional[Dict[str, Any]]) -> str:
    'Operation implementation.'
    if not snap:
        return ""
    lines = ["Health snapshot:"]
    try:
        dt = datetime.fromisoformat(snap["ts"])
        lines.append(f"  ts: {dt.strftime('%d.%m %H:%M')}")
    except (KeyError, ValueError):
        pass
    for k in sorted(snap.keys()):
        if k in META_KEYS:
            continue
        v = snap[k]
        if v is None or v == "":
            continue
        if k in string_keys() and isinstance(v, str) and len(v) > 280:
            v = v[:280].rstrip() + "…"
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def format_week_stats_for_llm(snaps: List[Dict[str, Any]]) -> str:
    'Operation implementation.'
    if not snaps:
        return ""
    lines = [pdmsg("auto_94eac10a67", _p1=len(snaps))]

    agg = week_numeric_aggregates(snaps)
    for field, stats in sorted(agg.items()):
        if field == "snapshot_count":
            continue
        if not isinstance(stats, dict):
            continue
        avg, mn, mx = stats["avg"], stats["min"], stats["max"]
        if stats["count"] > 1:
            lines.append(f"  {field}: avg={avg:.1f}, min={mn:.1f}, max={mx:.1f}")
        else:
            lines.append(f"  {field}: {avg:.1f}")

    return "\n".join(lines)
