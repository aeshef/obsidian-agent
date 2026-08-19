from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from planning_bot.services.reference_date import reference_today

# (comment)
# (comment)
LOGGING_HOUR_START = 10
LOGGING_HOUR_END = 2  # (comment)


def snap_in_logging_window(snap: Dict) -> bool:
    try:
        dt = datetime.fromisoformat(snap["ts"])
    except (KeyError, ValueError):
        return False
    h = dt.hour
    return h >= LOGGING_HOUR_START or h < LOGGING_HOUR_END


def filter_logging_window(snaps: List[Dict]) -> List[Dict]:
    return [s for s in snaps if snap_in_logging_window(s)]


_MAC_TS_FORMATS = (
    "%d %b %Y at %H:%M",
    "%d.%m.%Y, %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
)


def _parse_ts(s: str) -> Optional[datetime]:
    from shared.parsing.datetime_parse import parse_datetime

    return parse_datetime(s, strptime_formats=_MAC_TS_FORMATS)


# (comment)
from planning_bot.services.iphone_snapshot_names import (
    is_canonical_filename,
    is_legacy_filename,
    needs_rename_filename,
    parse_filename_ts,
)


def _parse_kv_block(text: str) -> Dict[str, str]:
    from shared.parsing.snapshot_kv import extract_kv_fields

    return extract_kv_fields(text, multiline_keys=frozenset())


def _fields_to_snap(fields: Dict[str, str], fallback_ts: Optional[datetime] = None) -> Optional[Dict]:
    ts = _parse_ts(fields.get("ts", "")) or fallback_ts
    if ts is None:
        return None
    battery: Optional[int] = None
    try:
        battery = int(fields["battery_pct"])
    except (KeyError, ValueError, TypeError):
        pass
    idle_sec: Optional[int] = None
    try:
        idle_sec = int(str(fields.get("idle_sec", "")).strip())
    except (ValueError, TypeError):
        pass
    window_title = (
        (fields.get("window_title") or fields.get("focus_window") or "").strip() or None
    )
    safari = (fields.get("safari_title") or "").strip()
    if safari.startswith("http"):
        try:
            safari = urlparse(safari).netloc or safari[:60]
        except Exception:
            safari = safari[:60]
    return {
        "ts": ts.isoformat(timespec="minutes"),
        "source": fields.get("source") or "mac",
        "app": fields.get("app") or None,
        "safari": safari or None,
        "wifi": fields.get("wifi") or None,
        "battery_pct": battery,
        "focus": fields.get("focus") or None,
        "weather": (fields.get("weather") or "").strip() or None,
        "window_title": window_title,
        "idle_sec": idle_sec,
        "active": idle_sec is not None and idle_sec < 120,
    }


def parse_context_file(path: Path) -> List[Dict]:
    """Parse all snapshots from a context file. Returns [] on error."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []

    fn_ts: Optional[datetime] = parse_filename_ts(path.name)

    snaps: List[Dict] = []
    # Split on --- separator, parse each block
    segments = re.split(r"(?m)^\s*---\s*$", text)
    for seg in segments:
        fields = _parse_kv_block(seg)
        if fields:
            snap = _fields_to_snap(fields, fn_ts)
            if snap:
                snaps.append(snap)

    # Fallback: whole file as one flat block
    if not snaps:
        fields = _parse_kv_block(text)
        if fields:
            snap = _fields_to_snap(fields, fn_ts)
            if snap:
                snaps.append(snap)

    return snaps


def _cutoff_now(days: int) -> datetime:
    now = datetime.now()
    return now - timedelta(days=max(0, int(days)))


def get_snapshots(mac_dir: Path, days: int = 7, logging_window_only: bool = False) -> List[Dict]:
    """Return all valid snapshots from the last `days` days, sorted by ts."""
    if not mac_dir.exists():
        return []
    cutoff = _cutoff_now(days)
    snaps: List[Dict] = []
    paths = sorted(
        p
        for p in mac_dir.glob("*.txt")
        if not p.name.startswith(".")
        and "{" not in p.name
        and "}" not in p.name
        and (is_canonical_filename(p.name) or needs_rename_filename(p.name))
    )
    seen = set()
    uniq_paths = []
    for p in paths:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            uniq_paths.append(p)
    from shared.query.ts import dt_ge, parse_iso_dt

    for path in uniq_paths:
        if "{" in path.name or "}" in path.name:
            continue  # broken shortcut output — skip
        for s in parse_context_file(path):
            dt = parse_iso_dt(s.get("ts", ""))
            if dt is None:
                continue
            if dt_ge(dt, cutoff):
                snaps.append(s)
    snaps.sort(key=lambda x: x.get("ts", ""))
    if logging_window_only:
        snaps = filter_logging_window(snaps)
    return snaps


def snap_local_date(snap: Dict) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(snap.get("ts", ""))).date()
    except (TypeError, ValueError, KeyError):
        return None


def get_today_snapshot(mac_dir: Path, logging_window_only: bool = True) -> Optional[Dict]:
    'Operation implementation.'
    ref = reference_today()
    allowed = {ref, ref - timedelta(days=1)}
    snaps = [
        s
        for s in get_snapshots(mac_dir, days=2, logging_window_only=logging_window_only)
        if (d := snap_local_date(s)) is not None and d in allowed
    ]
    same_day = [s for s in snaps if snap_local_date(s) == ref]
    if same_day:
        return same_day[-1]
    return snaps[-1] if snaps else None


def load_chat_snapshot_from_json(
    json_path: Path,
    *,
    as_of: date | None = None,
    allow_yesterday: bool = True,
) -> Optional[Dict]:
    """Latest snapshot for as_of from JSON today block; never falls back to stale recent."""
    if not json_path.exists():
        return None
    ref = as_of or reference_today()
    allowed = {ref}
    if allow_yesterday:
        allowed.add(ref - timedelta(days=1))
    try:
        import json

        data = json.loads(json_path.read_text(encoding="utf-8"))
        candidates: List[Tuple[date, Dict]] = []
        for snap in data.get("today") or []:
            day = snap_local_date(snap)
            if day is not None and day in allowed:
                candidates.append((day, snap))
        if not candidates:
            return None
        same_day = [s for d, s in candidates if d == ref]
        if same_day:
            return same_day[-1]
        yday = ref - timedelta(days=1)
        yday_snaps = [s for d, s in candidates if d == yday]
        return yday_snaps[-1] if yday_snaps else None
    except Exception:
        pass
    return None


_META_KEYS = frozenset({"ts", "source"})


def is_valid_mac_snapshot(snap: Dict | None) -> bool:
    """Mac shortcut context: app/focus/battery, not Health metrics."""
    if not snap:
        return False
    try:
        datetime.fromisoformat(str(snap["ts"]))
    except (KeyError, ValueError):
        return False
    if snap.get("app") or snap.get("focus"):
        return True
    if snap.get("battery_pct") is not None:
        return True
    if snap.get("safari") or snap.get("wifi"):
        return True
    return False


def mac_snapshot_score(snap: Dict) -> int:
    if not is_valid_mac_snapshot(snap):
        return -1
    return sum(
        1
        for k, v in snap.items()
        if k not in _META_KEYS and v not in (None, "")
    )


def week_aggregates(snaps: List[Dict]) -> Dict[str, object]:
    'Operation implementation.'
    apps: Dict[str, int] = {}
    focuses: Dict[str, int] = {}
    for s in snaps:
        if s.get("app"):
            apps[s["app"]] = apps.get(s["app"], 0) + 1
        if s.get("focus"):
            focuses[s["focus"]] = focuses.get(s["focus"], 0) + 1
    return {
        "apps_top": sorted(apps.items(), key=lambda x: -x[1])[:12],
        "focus_top": sorted(focuses.items(), key=lambda x: -x[1])[:8],
        "count": len(snaps),
    }


def format_for_llm(snap: Optional[Dict]) -> str:
    """Short block for LLM system context."""
    if not snap:
        return ""
    lines = [pdmsg("auto_f45e4e69c5")]
    try:
        dt = datetime.fromisoformat(snap["ts"])
        lines.append(pdmsg("auto_b4eebb2539", _p1=dt.strftime('%d.%m %H:%M')))
    except (KeyError, ValueError):
        pass
    _add = lambda k, label: lines.append(f"  {label}: {snap[k]}") if snap.get(k) else None
    _add("focus", pdmsg("auto_f1d3acb4fc"))
    _add("app", pdmsg("auto_90d840cbf5"))
    _add("window_title", "window")
    if snap.get("idle_sec") is not None:
        lines.append(f"  idle: {snap['idle_sec']}s")
    if snap.get("battery_pct") is not None:
        lines.append(pdmsg("auto_e352150d1f", _p1=snap['battery_pct']))
    _add("wifi", "wi-fi")
    _add("safari", "safari")
    _add("weather", pdmsg("auto_d57ba6e9b8"))
    return "\n".join(lines)


def format_week_stats_for_llm(snaps: List[Dict]) -> str:
    """Aggregates across a week of snapshots for the weekly review."""
    if not snaps:
        return ""
    apps: Dict[str, int] = {}
    focuses: Dict[str, int] = {}
    for s in snaps:
        if s.get("app"):
            apps[s["app"]] = apps.get(s["app"], 0) + 1
        if s.get("focus"):
            focuses[s["focus"]] = focuses.get(s["focus"], 0) + 1
    lines = [pdmsg("auto_8a47e8e90c", _p1=len(snaps))]
    if apps:
        top = sorted(apps.items(), key=lambda x: -x[1])[:5]
        lines.append(pdmsg("auto_fae9682263") + ", ".join(f"{a} ×{n}" for a, n in top))
    if focuses:
        top = sorted(focuses.items(), key=lambda x: -x[1])[:4]
        lines.append(pdmsg("auto_98a71d4f27") + ", ".join(f"{f} ×{n}" for f, n in top))
    return "\n".join(lines)
