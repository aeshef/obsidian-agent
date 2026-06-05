#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
import hashlib
import json
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = PROJECT_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from planning_bot.core.config import (
    CALENDAR_TXT_FILE,
    CALENDAR_JSON_FILE,
    CALENDAR_DASHBOARD_MD,
    CALENDAR_ANALYTICS_JSON,
    CALENDAR_INSIGHTS_CACHE,
)
from planning_bot.services.calendar_analytics import (
    analytics_stable_hash,
    compute_week_analytics,
    write_analytics_json,
)
from planning_bot.services.calendar_dashboard import write_meeting_focus_dashboard
from planning_bot.services.calendar_insights_llm import get_or_create_insights
from planning_bot.services.calendar_retention import (
    apply_retention,
    compact_calendar_txt,
    should_compact_txt,
)


def _dashboard_horizon_days() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int("planning_calendar", "sync_horizon_days", default=8)


def _build_and_write_dashboard(events: List[Dict], now_iso: str) -> None:
    'Operation implementation.'
    analytics = compute_week_analytics(
        events, date.today(), horizon_days=_dashboard_horizon_days()
    )
    write_analytics_json(CALENDAR_ANALYTICS_JSON, analytics)
    h = analytics_stable_hash(analytics)
    insights, _from_cache = get_or_create_insights(analytics, CALENDAR_INSIGHTS_CACHE, h, now_iso)
    write_meeting_focus_dashboard(CALENDAR_DASHBOARD_MD, now_iso, analytics, insights)

# DD.MM.YYYY HH:MM - HH:MM TITLE
_LINE_RE = re.compile(
    r"^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*(.*)$"
)
# "23 Apr 2026 at 17:52"
_TS_RE = re.compile(r"^\d{1,2} [A-Za-z]+ \d{4} at \d{2}:\d{2}$")

TAG_RE = re.compile(r"^\[([^\]]+)\]\s*")


def _event_id(date: str, start: str, end: str, title: str) -> str:
    'Operation implementation.'
    key = f"{date}|{start}|{end}|{title.strip().lower()[:40]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def _load_json(path: Path) -> Dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(pdmsg("auto_e3939e1bdb"), path, e)
    return {"meta": {"last_updated": None, "txt_last_parsed": None}, "events": []}


def _save_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _extract_txt_timestamp(txt_content: str) -> Optional[str]:
    'Operation implementation.'
    last: Optional[str] = None
    for line in txt_content.splitlines():
        line = line.strip()
        if not line or line == "---":
            continue
        if _TS_RE.match(line):
            try:
                dt = datetime.strptime(line, "%d %b %Y at %H:%M")
                last = dt.isoformat()
            except ValueError:
                pass
    return last


def _parse_event_line(line: str) -> Optional[Dict]:
    m = _LINE_RE.match(line.strip())
    if not m:
        return None
    day, month, year, start, end, title = m.groups()
    date_str = f"{year}-{month}-{day}"
    title = title.strip()

    is_cancelled = False
    if title.startswith(pdmsg("auto_d0edfc7fdc")):
        is_cancelled = True
        title = title[len(pdmsg("auto_d0edfc7fdc")) :].strip()

    is_allday = start == "00:00" and end == "23:59"

    tag = None
    tag_m = TAG_RE.match(title)
    if tag_m:
        tag = tag_m.group(1)
        title = title[tag_m.end() :].strip()

    return {
        "date": date_str,
        "start": start,
        "end": end,
        "title": title,
        "is_allday": is_allday,
        "is_cancelled": is_cancelled,
        "tag": tag,
    }


def _dedupe_block_events(raw: List[Dict]) -> Tuple[List[Dict], int]:
    """Collapse empty/title pairs inside one export block; keep double-bookings."""
    seen: Dict[str, Dict] = {}
    duplicates_dropped = 0
    for ev in raw:
        key = f"{ev['date']}|{ev['start']}|{ev['end']}"
        if key not in seen:
            seen[key] = ev
            continue
        existing = seen[key]
        if not existing["title"] and ev["title"]:
            seen[key] = ev
            duplicates_dropped += 1
        elif existing["title"] and not ev["title"]:
            duplicates_dropped += 1
        elif existing["title"] != ev["title"]:
            seen[f"{key}|{ev['title'][:20]}"] = ev
    return list(seen.values()), duplicates_dropped


def _split_export_blocks(txt_content: str) -> List[Tuple[Optional[datetime], List[str]]]:
    """Append-only iPhone export: --- / timestamp / --- / event lines."""
    blocks: List[Tuple[Optional[datetime], List[str]]] = []
    block_ts: Optional[datetime] = None
    block_lines: List[str] = []

    def flush() -> None:
        nonlocal block_ts, block_lines
        if block_ts is not None or block_lines:
            blocks.append((block_ts, block_lines))
        block_ts = None
        block_lines = []

    for line in txt_content.splitlines():
        stripped = line.strip()
        if _TS_RE.match(stripped):
            flush()
            try:
                block_ts = datetime.strptime(stripped, "%d %b %Y at %H:%M")
            except ValueError:
                block_ts = None
            continue
        if stripped == "---" and not block_lines:
            continue
        block_lines.append(line)

    flush()
    return blocks


def _event_end_dt(ev: Dict) -> Optional[datetime]:
    try:
        return datetime.strptime(f"{ev['date']} {ev['end']}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _store_block_events(
    events_map: Dict[str, Dict],
    block_events: List[Dict],
    block_ts: Optional[datetime] = None,
) -> None:
    for ev in block_events:
        base = _slot_key(ev)
        key = base
        if key in events_map and events_map[key].get("title") != ev.get("title"):
            title = (ev.get("title") or "")[:20]
            if title:
                key = f"{base}|{title}"
        events_map[key] = ev

        if block_ts is None:
            continue
        start_dt = _event_start_dt(ev)
        if start_dt is None or start_dt < block_ts:
            continue
        drop_same_start: List[str] = []
        for other_key, other in events_map.items():
            if other_key == key:
                continue
            if other["date"] != ev["date"] or other["start"] != ev["start"]:
                continue
            if _slot_key(other) == base:
                continue
            other_start = _event_start_dt(other)
            if other_start is not None and other_start >= block_ts:
                drop_same_start.append(other_key)
        for other_key in drop_same_start:
            del events_map[other_key]


def _parse_txt(txt_content: str) -> List[Dict]:
    """Parse export blocks; drop future slots missing from newer hourly snapshots."""
    blocks = _split_export_blocks(txt_content)
    events_map: Dict[str, Dict] = {}
    raw_total = 0
    duplicates_dropped = 0

    for block_ts, lines in blocks:
        raw: List[Dict] = []
        for line in lines:
            ev = _parse_event_line(line)
            if ev is not None:
                raw.append(ev)
        raw_total += len(raw)
        block_events, dropped = _dedupe_block_events(raw)
        duplicates_dropped += dropped
        block_base_keys = {_slot_key(e) for e in block_events}
        block_dates = {e["date"] for e in block_events}

        _store_block_events(events_map, block_events, block_ts)

        if block_ts is None or not block_dates:
            continue

        bases_present = {_slot_key(ev) for ev in events_map.values()}
        to_drop: List[str] = []
        for base_key in bases_present:
            date_str = base_key.split("|", 1)[0]
            if date_str not in block_dates:
                continue
            sample = next(ev for ev in events_map.values() if _slot_key(ev) == base_key)
            end_dt = _event_end_dt(sample)
            if end_dt is None or end_dt <= block_ts:
                continue
            if base_key in block_base_keys:
                continue
            title = (sample.get("title") or "").strip()
            start_dt = _event_start_dt(sample)
            if title and start_dt is not None and start_dt < block_ts:
                continue
            to_drop.append(base_key)

        if to_drop:
            drop_set = set(to_drop)
            for key in list(events_map.keys()):
                if _slot_key(events_map[key]) in drop_set:
                    del events_map[key]

    events = sorted(events_map.values(), key=lambda e: (e["date"], e["start"]))
    logger.info(
        pdmsg("auto_c24be15722"),
        raw_total,
        len(events),
        duplicates_dropped,
    )
    return events


def _slot_key(ev: Dict) -> str:
    return f"{ev['date']}|{ev['start']}|{ev['end']}"


def _parse_export_anchor(txt_ts: Optional[str]) -> Optional[datetime]:
    if not txt_ts:
        return None
    try:
        return datetime.fromisoformat(txt_ts)
    except ValueError:
        return None


def _event_start_dt(ev: Dict) -> Optional[datetime]:
    try:
        return datetime.strptime(f"{ev['date']} {ev['start']}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _reconcile_existing(
    existing_events: List[Dict],
    new_events: List[Dict],
    txt_ts: Optional[str],
) -> Tuple[List[Dict], int]:
    """Drop JSON slots absent from parsed txt snapshot for each touched calendar day."""
    del txt_ts  # block-aware parse is authoritative per day; anchor unused
    new_dates = {e["date"] for e in new_events}
    new_slot_keys = {_slot_key(e) for e in new_events}
    kept: List[Dict] = []
    removed = 0
    for ev in existing_events:
        if ev.get("is_cancelled"):
            kept.append(ev)
            continue
        if ev["date"] not in new_dates:
            kept.append(ev)
            continue
        if _slot_key(ev) in new_slot_keys:
            kept.append(ev)
            continue
        removed += 1
    return kept, removed


def _merge(existing_events: List[Dict], new_events: List[Dict]) -> Tuple[List[Dict], int, int]:
    'Operation implementation.'
    now_iso = datetime.now().isoformat(timespec="seconds")
    existing_by_id: Dict[str, Dict] = {e["id"]: e for e in existing_events if "id" in e}

    added, updated = 0, 0
    for ev in new_events:
        ev_id = _event_id(ev["date"], ev["start"], ev["end"], ev["title"])
        ev["id"] = ev_id

        if ev_id not in existing_by_id:
            ev["added_at"] = now_iso
            existing_by_id[ev_id] = ev
            added += 1
        else:
            old = existing_by_id[ev_id]
            if old.get("is_cancelled") != ev.get("is_cancelled"):
                old["is_cancelled"] = ev["is_cancelled"]
                old["updated_at"] = now_iso
                updated += 1

    merged = sorted(existing_by_id.values(), key=lambda e: (e["date"], e["start"]))
    return merged, added, updated


def _dedupe_same_time_slot(events: List[Dict]) -> List[Dict]:
    'Operation implementation.'
    best: Dict[str, Dict] = {}

    def score(ev: Dict) -> Tuple[int, int, str]:
        not_can = 0 if ev.get("is_cancelled") else 1
        tlen = len(ev.get("title") or "")
        added = ev.get("added_at") or ""
        return (not_can, tlen, added)

    for ev in events:
        k = f"{ev['date']}|{ev['start']}|{ev['end']}"
        cur = best.get(k)
        if cur is None or score(ev) > score(cur):
            best[k] = ev
    return sorted(best.values(), key=lambda e: (e["date"], e["start"]))


def _sync_from_txt(
    data: Dict,
    txt_content: str,
    txt_ts: Optional[str],
) -> Tuple[Dict, List[Dict], bool, int, int, int]:
    """Reconcile + merge txt snapshot into JSON. Returns changed flag."""
    new_events = _parse_txt(txt_content)
    existing, dropped = _reconcile_existing(data.get("events", []), new_events, txt_ts)
    if dropped:
        logger.info("calendar reconcile: dropped %s phantom future slot(s)", dropped)
    merged, added, updated = _merge(existing, new_events)
    changed = bool(dropped or added or updated)
    now_iso = datetime.now().isoformat(timespec="seconds")
    if changed:
        data["meta"]["last_updated"] = now_iso
        data["meta"]["txt_last_parsed"] = txt_ts or now_iso
        data["meta"]["total_events"] = len(merged)
        data["events"] = merged
    return data, merged, changed, dropped, added, updated


def run_calendar_sync() -> bool:
    'Operation implementation.'
    if not CALENDAR_TXT_FILE.exists():
        logger.info(pdmsg("auto_b198725f3a"), CALENDAR_TXT_FILE)
        return True

    with open(CALENDAR_TXT_FILE, "r", encoding="utf-8") as f:
        txt_content = f.read()

    txt_ts = _extract_txt_timestamp(txt_content)

    data = _load_json(CALENDAR_JSON_FILE)
    last_parsed = data["meta"].get("txt_last_parsed")
    unchanged_ts = bool(txt_ts and txt_ts == last_parsed)

    if unchanged_ts:
        logger.info(pdmsg("auto_db56dcef25"), txt_ts)
        print(pdmsg("auto_80593794b5"), flush=True)
    else:
        print(pdmsg("auto_c8a1e8f8bb"), flush=True)
        print(pdmsg("auto_779ae56025", CALENDAR_TXT_FILE={CALENDAR_TXT_FILE}), flush=True)
        print(pdmsg("auto_8fe3e14bf5", _p1=last_parsed or pdmsg('auto_f0cf0b41cc')), flush=True)
        print(pdmsg("auto_81a548769a", txt_ts={txt_ts}), flush=True)

    data, merged, changed, dropped, added, updated = _sync_from_txt(
        data, txt_content, txt_ts
    )

    now_iso = datetime.now().isoformat(timespec="seconds")
    data, moved, detail_n = apply_retention(data)
    if moved:
        logger.info("calendar retention: moved %s events to archive, detail=%s", moved, detail_n)
    if changed or moved:
        _save_json(CALENDAR_JSON_FILE, data)

    if not unchanged_ts:
        line_count = txt_content.count("\n") + (1 if txt_content else 0)
        if should_compact_txt(line_count):
            compacted, compact_dropped = compact_calendar_txt(txt_content)
            if compact_dropped > 0 and compacted != txt_content:
                CALENDAR_TXT_FILE.write_text(compacted, encoding="utf-8")
                logger.info(
                    "calendar txt compacted: dropped %s lines before %s",
                    compact_dropped,
                    data["meta"].get("detail_cutoff"),
                )

    try:
        _build_and_write_dashboard(data.get("events", merged), now_iso)
        print(pdmsg("auto_f2964bb97c", CALENDAR_DASHBOARD_MD={CALENDAR_DASHBOARD_MD}), flush=True)
    except Exception as e:
        logger.warning(pdmsg("auto_58b2a8d2f2"), e)

    if changed:
        print(pdmsg("auto_3d9d657bf4", _p1=added, _p3=updated, _p5=len(merged)), flush=True)
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_calendar_sync()
    sys.exit(0 if success else 1)
