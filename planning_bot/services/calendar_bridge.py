"""Durable server queue; native Calendar writes are acknowledged by the Mac worker."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from shared.agent.config import agent_config_dir
from shared.yaml_config import load_merged_config


def config() -> dict:
    return load_merged_config(str(agent_config_dir()), "calendar_bridge") or {}


def queue_path() -> Path:
    return agent_config_dir().parent.parent / "calendar_bridge.db"


def connection(path: Path | None = None) -> sqlite3.Connection:
    p = path or queue_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(p, timeout=15)
    os.chmod(p, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY, actor INTEGER NOT NULL, payload TEXT NOT NULL,
        status TEXT NOT NULL, created REAL NOT NULL, lease_until REAL NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0, lease TEXT, result TEXT)""")
    db.execute("CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY, heartbeat REAL, report TEXT)")
    return db


def normalize(title: str, start: str, end: str, calendar: str = "", notes: str = "", location: str = "") -> dict:
    cfg = config()
    if not title.strip() or len(title) > cfg["max_title_length"]:
        raise ValueError("invalid_title")
    if len(notes) > cfg["max_notes_length"] or len(location) > cfg["max_title_length"]:
        raise ValueError("text_too_long")
    a, b = (datetime.fromisoformat(s.replace("Z", "+00:00")) for s in (start, end))
    if a.tzinfo is None or b.tzinfo is None:
        raise ValueError("timezone_offset_required")
    if not 0 < (b - a).total_seconds() <= cfg["max_duration_days"] * 86400:
        raise ValueError("invalid_duration")
    return dict(title=title.strip(), start=a.astimezone(timezone.utc).isoformat(),
                end=b.astimezone(timezone.utc).isoformat(), calendar=calendar.strip() or cfg["default_calendar"],
                notes=notes, location=location)


def enqueue(actor: int, payload: dict, path: Path | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    rid = hashlib.sha256(f"{actor}:{body}".encode()).hexdigest()
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM requests WHERE id=? AND actor=?", (rid, actor)).fetchone()
        if row:
            return public_result(row)
        if db.execute("SELECT count(*) FROM requests WHERE status IN ('queued','processing')").fetchone()[0] >= config()["max_pending"]:
            raise ValueError("queue_full")
        db.execute("INSERT INTO requests(id,actor,payload,status,created) VALUES (?,?,?,'queued',?)",
                   (rid, actor, body, time.time()))
        return {"request_id": rid, "status": "queued", "created_in_calendar": False}


def public_result(row) -> dict:
    result = json.loads(row["result"]) if row["result"] else {}
    return {"request_id": row["id"], "status": row["status"],
            "created_in_calendar": row["status"] == "created", **result}


def status(actor: int, rid: str, path: Path | None = None) -> dict:
    with connection(path) as db:
        row = db.execute("SELECT * FROM requests WHERE id=? AND actor=?", (rid, actor)).fetchone()
        return public_result(row) if row else {"status": "not_found"}


def rpc(message: dict, path: Path | None = None) -> dict:
    """SSH-only worker protocol; never exposed as an agent tool."""
    cfg = config()
    if not cfg.get("enabled"):
        return {"status": "disabled"}
    if message.get("action") == "snapshot":
        from planning_bot.services.calendar_snapshot import ingest
        from planning_bot.core.config import CALENDAR_JSON_FILE
        data = ingest(message["snapshot"], CALENDAR_JSON_FILE,
                      os.environ.get("CALENDAR_TZ") or os.environ.get("TIMEZONE") or "UTC")
        return {"ok": True, "captured_at": data["meta"]["source_captured_at"], "count": len(data["events"])}
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        action = message.get("action")
        if action == "claim":
            if not cfg.get("write_enabled"):
                return {"request": None}
            row = db.execute("SELECT * FROM requests WHERE status='queued' OR (status='processing' AND lease_until<?) ORDER BY created LIMIT 1", (time.time(),)).fetchone()
            if not row:
                return {"request": None}
            lease = uuid.uuid4().hex
            db.execute("UPDATE requests SET status='processing',lease=?,lease_until=?,attempts=attempts+1 WHERE id=?",
                       (lease, time.time() + cfg["lease_seconds"], row["id"]))
            return {"request": {"request_id": row["id"], "lease": lease,
                                "allow_create": row["attempts"] == 0, **json.loads(row["payload"])}}
        if action == "ack":
            result = message["result"]
            state = result.get("status")
            if state not in ("created", "failed", "outcome_unknown"):
                raise ValueError("invalid_result_status")
            if state == "created" and not result.get("event_id"):
                raise ValueError("event_id_required")
            changed = db.execute("UPDATE requests SET status=?,result=? WHERE id=? AND lease=? AND status='processing'",
                                 (state, json.dumps(result), message["request_id"], message["lease"])).rowcount
            return {"acknowledged": bool(changed)}
        if action == "heartbeat":
            db.execute("INSERT OR REPLACE INTO worker VALUES (1,?,?)", (time.time(), json.dumps(message.get("report", {}))))
            return {"ok": True}
        raise ValueError("unknown_action")
