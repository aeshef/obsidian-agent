"""Roll up calendar events older than detail window; compact append-only export txt."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from shared.yaml_config import load_merged_config

_CFG_DIR = Path(__file__).resolve().parent.parent / "config"
_LINE_RE = re.compile(
    r"^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*(.*)$"
)
_TS_RE = re.compile(r"^\d{1,2} [A-Za-z]+ \d{4} at \d{2}:\d{2}$")


@lru_cache(maxsize=1)
def retention_config() -> dict[str, Any]:
    return load_merged_config(str(_CFG_DIR), "calendar_retention") or {}


def detail_months() -> int:
    raw = retention_config().get("detail_months", 3)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 3


def detail_cutoff(anchor: date | None = None) -> date:
    """First day of the month (detail_months - 1) months before anchor's month."""
    today = anchor or date.today()
    y, m = today.year, today.month
    shift = detail_months() - 1
    m -= shift
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _event_date(ev: dict) -> date | None:
    try:
        return datetime.strptime(str(ev["date"]), "%Y-%m-%d").date()
    except (ValueError, KeyError, TypeError):
        return None


def _event_minutes(ev: dict) -> int:
    if ev.get("is_allday") or ev.get("is_cancelled"):
        return 0
    try:
        t0 = datetime.strptime(ev["start"], "%H:%M")
        t1 = datetime.strptime(ev["end"], "%H:%M")
        m = max(0, int((t1 - t0).total_seconds() // 60))
        return m if 0 < m <= 16 * 60 else 0
    except (ValueError, KeyError):
        return 0


def build_monthly_rollups(events: list[dict]) -> list[dict[str, Any]]:
    """Aggregate timed meetings per calendar month (for archive layer)."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        d = _event_date(ev)
        if d is None:
            continue
        by_month[d.strftime("%Y-%m")].append(ev)

    out: list[dict[str, Any]] = []
    for month in sorted(by_month.keys()):
        month_events = by_month[month]
        timed = [e for e in month_events if not e.get("is_allday") and not e.get("is_cancelled")]
        minutes = sum(_event_minutes(e) for e in timed)
        tags: Counter[str] = Counter()
        for e in timed:
            tags[str(e.get("tag") or "other")] += _event_minutes(e)
        out.append(
            {
                "month": month,
                "meeting_count": len(timed),
                "meeting_minutes": minutes,
                "meeting_hours": round(minutes / 60, 2),
                "allday_count": sum(1 for e in month_events if e.get("is_allday")),
                "cancelled_count": sum(1 for e in month_events if e.get("is_cancelled")),
                "tags_minutes": dict(tags),
            }
        )
    return out


def _merge_monthly(existing: list[dict], new: list[dict]) -> list[dict]:
    by_m = {str(x["month"]): x for x in existing if x.get("month")}
    for row in new:
        m = str(row.get("month") or "")
        if not m:
            continue
        if m in by_m:
            prev = by_m[m]
            prev["meeting_count"] = int(prev.get("meeting_count", 0)) + int(row.get("meeting_count", 0))
            prev["meeting_minutes"] = int(prev.get("meeting_minutes", 0)) + int(row.get("meeting_minutes", 0))
            prev["meeting_hours"] = round(prev["meeting_minutes"] / 60, 2)
            prev["allday_count"] = int(prev.get("allday_count", 0)) + int(row.get("allday_count", 0))
            prev["cancelled_count"] = int(prev.get("cancelled_count", 0)) + int(row.get("cancelled_count", 0))
            tags = Counter(prev.get("tags_minutes") or {})
            tags.update(row.get("tags_minutes") or {})
            prev["tags_minutes"] = dict(tags)
        else:
            by_m[m] = row
    return [by_m[k] for k in sorted(by_m.keys())]


def apply_retention(data: dict, anchor: date | None = None) -> tuple[dict, int, int]:
    """
    Move events before detail_cutoff into data['archive']['monthly'].
    Returns (data, moved_count, detail_count).
    """
    cutoff = detail_cutoff(anchor)
    events = list(data.get("events") or [])
    recent: list[dict] = []
    old: list[dict] = []
    for ev in events:
        d = _event_date(ev)
        if d is None or d >= cutoff:
            recent.append(ev)
        else:
            old.append(ev)

    archive = dict(data.get("archive") or {})
    monthly = list(archive.get("monthly") or [])
    if old:
        monthly = _merge_monthly(monthly, build_monthly_rollups(old))
    archive["monthly"] = monthly
    archive["detail_cutoff"] = cutoff.isoformat()
    archive["detail_months"] = detail_months()
    archive["rolled_at"] = datetime.now().isoformat(timespec="seconds")

    data["events"] = recent
    data["archive"] = archive
    meta = data.setdefault("meta", {})
    meta["detail_cutoff"] = cutoff.isoformat()
    meta["archive_months"] = len(monthly)
    return data, len(old), len(recent)


def format_archive_range_summary(
    archive: dict | None,
    start: date,
    end: date,
) -> str:
    """Text block for LLM/tools when range is mostly outside detail events."""
    if not archive:
        return ""
    monthly = archive.get("monthly") or []
    if not monthly:
        return ""
    lines = [
        f"Calendar archive summary ({start.isoformat()} – {end.isoformat()}), monthly totals:"
    ]
    for row in monthly:
        m = str(row.get("month") or "")
        if not m:
            continue
        try:
            y, mo = map(int, m.split("-", 1))
            month_start = date(y, mo, 1)
            if mo == 12:
                month_end = date(y, 12, 31)
            else:
                month_end = date(y, mo + 1, 1) - timedelta(days=1)
        except ValueError:
            continue
        if month_end < start or month_start > end:
            continue
        lines.append(
            f"  {m}: {row.get('meeting_count', 0)} timed meetings, "
            f"{row.get('meeting_hours', 0)}h"
        )
    return "\n".join(lines) if len(lines) > 1 else ""


def compact_calendar_txt(txt_content: str, anchor: date | None = None) -> tuple[str, int]:
    """
    Rewrite export txt keeping export timestamp blocks and event lines >= cutoff.
    Returns (new_content, lines_dropped).
    """
    cutoff = detail_cutoff(anchor)
    out: list[str] = []
    dropped = 0
    last_ts_block: list[str] = []

    for line in txt_content.splitlines():
        stripped = line.strip()
        if _TS_RE.match(stripped):
            if last_ts_block:
                out.extend(last_ts_block)
            last_ts_block = [line]
            continue
        if stripped == "---":
            if last_ts_block:
                out.extend(last_ts_block)
                last_ts_block = []
            out.append(line)
            continue
        m = _LINE_RE.match(stripped)
        if not m:
            if last_ts_block and not m:
                last_ts_block.append(line)
            else:
                out.append(line)
            continue
        day, month, year = m.group(1), m.group(2), m.group(3)
        try:
            ev_d = date(int(year), int(month), int(day))
        except ValueError:
            out.append(line)
            continue
        if ev_d >= cutoff:
            if last_ts_block:
                out.extend(last_ts_block)
                last_ts_block = []
            out.append(line)
        else:
            dropped += 1

    if last_ts_block:
        out.extend(last_ts_block)
    new_text = "\n".join(out)
    if txt_content.endswith("\n"):
        new_text += "\n"
    return new_text, dropped


def should_compact_txt(line_count: int) -> bool:
    cfg = retention_config()
    if not cfg.get("compact_txt_after_sync", True):
        return False
    try:
        threshold = int(cfg.get("txt_min_lines_to_compact", 5000))
    except (TypeError, ValueError):
        threshold = 5000
    return line_count >= threshold
