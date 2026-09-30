"""Reconcile explicit complete native snapshots, including empty days and moved events."""
from __future__ import annotations
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo


def parse_date(value: str) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("snapshot_requires_timezone")
    return d


def reconcile(data: dict, snapshot: dict, timezone: str) -> dict:
    if snapshot.get("complete") is not True or snapshot.get("schema_version") != 1:
        raise ValueError("incomplete_snapshot")
    start, end, captured = (parse_date(snapshot[k]) for k in ("window_start", "window_end", "captured_at"))
    if end <= start:
        raise ValueError("invalid_window")
    last = data.get("meta", {}).get("source_captured_at")
    if last and captured < parse_date(last):
        raise ValueError("out_of_order_snapshot")
    tz = ZoneInfo(timezone)
    rows = snapshot["events"]
    if not isinstance(rows, list) or not isinstance(snapshot["calendars"], list):
        raise ValueError("invalid_snapshot")
    cal_ids = {c["id"] for c in snapshot["calendars"]}
    prior = {e.get("id"): e for e in data.get("events", [])}
    incoming = []
    for ev in rows:
        a, b = parse_date(ev["start_at"]), parse_date(ev["end_at"])
        if b <= a or b <= start or a >= end or ev["calendar_id"] not in cal_ids:
            raise ValueError("invalid_snapshot_event")
        rid = hashlib.sha256(f"{ev['calendar_id']}:{ev['native_id']}:{ev['occurrence_start']}".encode()).hexdigest()
        local_a, local_b = a.astimezone(tz), b.astimezone(tz)
        row = {**prior.get(rid, {}), **ev, "id": rid, "date": local_a.date().isoformat(),
               "start": local_a.strftime("%H:%M"), "end": local_b.strftime("%H:%M"),
               "end_date": local_b.date().isoformat(), "source": "apple_calendar"}
        old = prior.get(rid, {})
        if old.get("title") != ev.get("title"):
            row.pop("activity_type", None)
        incoming.append(row)
    # Replace the whole declared coverage, not only dates that happen to have events.
    kept = []
    for e in data.get("events", []):
        if e.get("start_at") and e.get("end_at"):
            overlap = parse_date(e["start_at"]) < end and parse_date(e["end_at"]) > start
        else:
            day = e.get("date", "")
            overlap = start.astimezone(tz).date().isoformat() <= day < end.astimezone(tz).date().isoformat()
        if not overlap:
            kept.append(e)
    from planning_bot.services.calendar_retention import build_monthly_rollups, _merge_monthly
    expired = [e for e in kept if e.get("date", "") < start.astimezone(tz).date().isoformat()]
    kept = [e for e in kept if e not in expired]
    archive = dict(data.get("archive", {}))
    # The initial native window can reach into already rolled-up legacy months.
    # Preserve those totals without adding the same historical events a second time.
    sealed = archive.get("sealed_legacy_months", [])
    if data.get("meta", {}).get("source") != "apple_calendar":
        sealed = [row["month"] for row in archive.get("monthly", [])]
    archive["sealed_legacy_months"] = sealed
    rollups = [r for r in build_monthly_rollups(expired) if r["month"] not in sealed]
    archive["monthly"] = _merge_monthly(list(archive.get("monthly", [])), rollups)
    archive["detail_cutoff"] = start.astimezone(tz).date().isoformat()
    data = dict(data)
    data["archive"] = archive
    data["events"] = sorted(kept + incoming, key=lambda e: (e["date"], e["start"], e["id"]))
    data["meta"] = {**data.get("meta", {}), "source": "apple_calendar", "source_captured_at": snapshot["captured_at"],
                    "last_checked": snapshot["captured_at"], "last_updated": snapshot["captured_at"],
                    "coverage_start": snapshot["window_start"], "coverage_end": snapshot["window_end"],
                    "complete": True, "calendars": snapshot["calendars"], "total_events": len(data["events"])}
    return data


def ingest(snapshot: dict, path, timezone: str) -> dict:
    """Atomic native import, independent of slow chart/LLM jobs."""
    import json
    import os
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {}
        data = reconcile(data, snapshot, timezone)
        temp = path.with_suffix(f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False))
        os.chmod(temp, 0o600)
        temp.replace(path)
        return data


def enrich(path, events: list[dict]) -> None:
    """Merge only matching classification fields; never replace a newer event snapshot."""
    import json
    import os
    import fcntl
    labels = {e['id']: e for e in events if e.get('activity_type')}
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text())
        for row in data.get('events', []):
            label = labels.get(row['id'])
            if label and label.get('title') == row.get('title'):
                for key in ('activity_type', 'activity_sig'):
                    if key in label: row[key] = label[key]
        temp = path.with_suffix(f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False));temp.replace(path)
