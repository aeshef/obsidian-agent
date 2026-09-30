"""Durable, idempotent Mac event ingestion and bounded activity accounting."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from shared.agent.config import agent_config_dir
from shared.yaml_config import load_merged_config


def config():
    return load_merged_config(str(agent_config_dir()), "mac_capture")


def enabled():
    from shared.capabilities.profile import get_capabilities
    return config().get("enabled") and get_capabilities().connector("mac_context")


def connection(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20)
    os.chmod(path, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, ts REAL NOT NULL, body TEXT NOT NULL,
                                        ack INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS event_time ON events(ts);
        CREATE TABLE IF NOT EXISTS hours(hour TEXT PRIMARY KEY, body TEXT NOT NULL);
    ''')
    columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
    if "materialized" not in columns:
        db.execute("ALTER TABLE events ADD COLUMN materialized INTEGER NOT NULL DEFAULT 0")
        db.commit()
    return db


def validate(row):
    if not isinstance(row, dict):
        raise ValueError("invalid_event")
    for key in ("id", "session_id"):
        uuid.UUID(row[key])
    dt = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.timestamp() > time.time() + 300:
        raise ValueError("invalid_time")
    if row["kind"] not in {"start", "heartbeat", "app_changed", "sleep", "wake", "session_inactive", "session_active"}:
        raise ValueError("invalid_kind")
    if type(row["awake"]) is not bool or type(row["session_active"]) is not bool:
        raise ValueError("invalid_state")
    idle = float(row["idle_sec"])
    if not math.isfinite(idle) or idle < 0:
        raise ValueError("invalid_idle")
    clean = {k: row[k] for k in ("id", "session_id", "ts", "kind", "awake", "session_active")}
    clean.update(app=str(row.get("app", ""))[:300], bundle_id=str(row.get("bundle_id", ""))[:300],
                 idle_sec=idle, source="mac_native_v1")
    return clean, dt.timestamp()


def ingest(db, rows, *, ack=False):
    validated = [validate(row) for row in rows]
    with db:
        for row, ts in validated:
            body = json.dumps(row, sort_keys=True, ensure_ascii=False)
            existing = db.execute("SELECT body FROM events WHERE id=?", (row["id"],)).fetchone()
            if existing and existing["body"] != body:
                raise ValueError("event_id_conflict")
            db.execute("INSERT OR IGNORE INTO events(id,ts,body,ack) VALUES(?,?,?,?)", (row["id"], ts, body, int(ack)))
    return [r[0]["id"] for r in validated]


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False)); os.chmod(temp, 0o600)
    temp.replace(path)


def materialize(db, directory: Path, days: set[str], cfg):
    """Bridge-owned daily files; existing Shortcut files remain untouched."""
    tz = ZoneInfo(os.environ.get("TIMEZONE") or "UTC")
    directory.mkdir(parents=True, exist_ok=True)
    for day in sorted(days):
        start = datetime.fromisoformat(day).replace(tzinfo=tz)
        end = start + timedelta(days=1)
        rows = [json.loads(r[0]) for r in db.execute("SELECT body FROM events WHERE ts>=? AND ts<? ORDER BY ts,id",
                                                  (start.timestamp(), end.timestamp()))]
        blocks = []
        # Legacy tools count snapshots; expose the regular heartbeats only.
        for row in rows:
            if row["kind"] not in {"start", "heartbeat"}:
                continue
            local = datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).astimezone(tz)
            fields = {**row, "ts": local.isoformat(), "active": row["awake"] and row["session_active"] and row["idle_sec"] < cfg["idle_seconds"]}
            blocks.append("---\n" + "\n".join(f"{k}: {str(v).lower() if isinstance(v, bool) else str(v).replace(chr(10), ' ')}" for k, v in fields.items()) + "\n")
        path = directory / f"{day}, 00-00_9001.txt"
        temp = path.with_suffix(".tmp"); temp.write_text("".join(blocks)); temp.replace(path)


def aggregate(db, cfg, since: float | None = None):
    """Rebuild retained hours; retain older aggregates when raw rows expire."""
    floor = int(since)//3600*3600 if since is not None else None
    if floor is None:
        raw = db.execute("SELECT body FROM events ORDER BY ts,id").fetchall()
    else:
        raw = list(db.execute("SELECT body FROM events WHERE ts<? ORDER BY ts DESC,id DESC LIMIT 1", (floor,)))
        raw += list(db.execute("SELECT body FROM events WHERE ts>=? ORDER BY ts,id", (floor,)))
    rows = [json.loads(r[0]) for r in raw]
    buckets = {}
    for first, second in zip(rows, rows[1:]):
        a = datetime.fromisoformat(first["ts"].replace("Z", "+00:00")).timestamp()
        b = datetime.fromisoformat(second["ts"].replace("Z", "+00:00")).timestamp()
        if b <= a:
            continue
        known = (first["session_id"] == second["session_id"] and (not first["awake"] or b-a <= cfg["max_interval_seconds"]))
        state = "unknown" if not known else "sleep" if not first["awake"] else "inactive" if not first["session_active"] else "idle" if first["idle_sec"] >= cfg["idle_seconds"] else "active"
        while a < b:
            boundary = (int(a)//3600+1)*3600
            stop = min(b, boundary)
            if floor is not None and a < floor:
                a = min(b, float(floor))
                continue
            key = datetime.fromtimestamp(a, timezone.utc).strftime("%Y-%m-%dT%H:00:00+00:00")
            bucket = buckets.setdefault(key, {"states": {}, "apps": {}})
            bucket["states"][state] = bucket["states"].get(state, 0) + stop-a
            if state == "active":
                app = first["bundle_id"] or first["app"] or "unknown"
                bucket["apps"][app] = bucket["apps"].get(app, 0) + stop-a
            a = stop
    with db:
        for key, body in buckets.items():
            db.execute("INSERT OR REPLACE INTO hours VALUES(?,?)", (key, json.dumps(body)))


def maintain(db, directory, cfg, *, local_only=False):
    # Keep a complete boundary day plus preceding context; never prune pending events.
    cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=cfg["raw_days"] + 1)
    with db:
        db.execute("DELETE FROM events WHERE (ack=1 OR (? AND materialized=1)) AND ts<?", (local_only, cutoff.timestamp()))
        db.execute("DELETE FROM hours WHERE hour<?", ((datetime.now(timezone.utc)-timedelta(days=cfg["aggregate_days"])).isoformat(),))
    for path in directory.glob("????-??-??, 00-00_9001.txt"):
        if path.name[:10] < cutoff.date().isoformat():
            # Do not remove a materialized day with pending delivery.
            pending = db.execute("SELECT 1 FROM events WHERE ack=0 AND ts<? LIMIT 1", (cutoff.timestamp(),)).fetchone()
            if not pending:
                path.unlink()


def report(db, cfg):
    latest = db.execute("SELECT MAX(ts) FROM events").fetchone()[0]
    pending = db.execute("SELECT count(*) FROM events WHERE ack=0").fetchone()[0]
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "last_capture": datetime.fromtimestamp(latest, timezone.utc).isoformat() if latest else None,
            "capture_age_seconds": round(time.time()-latest) if latest else None,
            "pending_events": pending, "status": "missing" if latest is None else "stale" if time.time()-latest > cfg["stale_seconds"] else "ok"}


def server_db():
    return agent_config_dir().parent.parent / "mac_capture.db"


def summary(start_day: str = "", end_day: str = ""):
    """Whole local calendar days over UTC-hour aggregates; expose missing coverage."""
    if not enabled():
        return {"status": "disabled"}
    cfg = config()
    now = datetime.now(timezone.utc)
    tz = ZoneInfo(os.environ.get("TIMEZONE") or "UTC")
    start = datetime.fromisoformat(start_day or now.astimezone(tz).date().isoformat()).replace(tzinfo=tz)
    end = datetime.fromisoformat(end_day or start.date().isoformat()).replace(tzinfo=tz) + timedelta(days=1)
    if start >= end or (end-start).days > cfg["query_days_max"]:
        raise ValueError("invalid_range")
    if not server_db().exists():
        return {"status": "missing"}
    with connection(server_db()) as db:
        states, apps = {}, {}
        for raw, in db.execute("SELECT body FROM hours WHERE hour>=? AND hour<? ORDER BY hour", (start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat())):
            row = json.loads(raw)
            for dest, key in ((states, "states"), (apps, "apps")):
                for name, seconds in row[key].items():
                    dest[name] = dest.get(name, 0) + seconds
        elapsed = max(0, (min(now, end)-start).total_seconds())
        covered = sum(v for k,v in states.items() if k != "unknown")
        return {**report(db, cfg), "timezone": str(tz), "start": start.isoformat(), "end": end.isoformat(),
                "coverage_seconds": round(covered), "missing_seconds": round(max(0, elapsed-covered)),
                "state_seconds": {k: round(v) for k,v in states.items()},
                "active_app_seconds": {k: round(v) for k,v in sorted(apps.items(), key=lambda p: -p[1])},
                "activity_is_estimated": True}


def receive(rows):
    if not enabled():
        return {"status": "disabled", "accepted": []}
    cfg = config()
    if not isinstance(rows, list) or len(rows) > cfg["batch_size"]:
        raise ValueError("invalid_batch")
    from planning_bot.core.config import CONTEXT_MAC_DIR, VAULT_PATH
    tz = ZoneInfo(os.environ.get("TIMEZONE") or "UTC")
    with connection(server_db()) as db:
        ids = ingest(db, rows, ack=True)
        days = {datetime.fromisoformat(r["ts"].replace("Z", "+00:00")).astimezone(tz).date().isoformat() for r in rows}
        materialize(db, CONTEXT_MAC_DIR, days, cfg)
        if rows:
            aggregate(db, cfg, min(datetime.fromisoformat(r["ts"].replace("Z", "+00:00")).timestamp() for r in rows)-cfg["max_interval_seconds"])
        maintain(db, CONTEXT_MAC_DIR, cfg)
        atomic_json(Path(VAULT_PATH)/".sync/mac_capture_status.json", report(db, cfg))
    return {"accepted": ids}
