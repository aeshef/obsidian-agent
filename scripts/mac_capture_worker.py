"""Drain native spool locally, then deliver with explicit idempotent acknowledgement."""
from __future__ import annotations
import fcntl
import json
import os
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from planning_bot.services.mac_capture import (aggregate, atomic_json, config, connection,
    enabled, ingest, maintain, materialize, report)


def remote(rows, cfg):
    command = f"cd {shlex.quote(os.environ['SERVER_BOTS'])} && ./scripts/oa-python.sh scripts/mac_capture_rpc.py"
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", os.environ["SERVER"], command],
                       input=json.dumps({"events": rows}), text=True, capture_output=True, timeout=cfg["rpc_timeout_seconds"])
    if p.returncode:
        raise RuntimeError("transport_failed")
    return json.loads(p.stdout)


def drain(db, spool):
    errors = []
    for path in sorted(spool.glob("*.json")):
        try:
            ingest(db, [json.loads(path.read_text())])
            path.unlink()  # commit precedes deletion; replay after a crash is safe
        except Exception as exc:
            errors.append(type(exc).__name__)
    return errors


def deliver(db, cfg, sender=remote):
    batch = [json.loads(r[0]) for r in db.execute("SELECT body FROM events WHERE ack=0 ORDER BY ts,id LIMIT ?", (cfg["batch_size"],))]
    if not batch:
        return 0
    response = sender(batch, cfg)
    expected = {r["id"] for r in batch}
    accepted = set(response.get("accepted", []))
    if not accepted <= expected:
        raise ValueError("invalid_ack")
    with db:
        db.executemany("UPDATE events SET ack=1 WHERE id=?", [(rid,) for rid in accepted])
    if accepted != expected:
        raise RuntimeError("partial_ack")
    return len(accepted)


def run():
    if not enabled():
        return {"status": "disabled"}
    from planning_bot.core.config import CONTEXT_MAC_DIR, VAULT_PATH
    cfg = config()
    state = Path(os.environ.get("MAC_CAPTURE_STATE", str(Path.home()/"Library/Application Support/obsidian-agent/mac-capture")))
    state.mkdir(parents=True, exist_ok=True)
    # Local-only mode stays outside the vault so the pre-existing bulk sync cannot upload it.
    output_dir = CONTEXT_MAC_DIR if cfg.get("upload_enabled") else state/"local-preview"
    lock = (state/"worker.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {"status": "busy"}
    tz = ZoneInfo(os.environ.get("TIMEZONE") or "UTC")
    with connection(state/"events.db") as db:
        errors = drain(db, state/"outbox")
        # Pending days are rematerialized until delivery succeeds, including failed local writes.
        local_only = not cfg.get("upload_enabled")
        rows = db.execute("SELECT id,ts FROM events WHERE materialized=0" if local_only else "SELECT id,ts FROM events WHERE ack=0").fetchall()
        days = {datetime.fromtimestamp(r["ts"], tz).date().isoformat() for r in rows}
        result = report(db, cfg)
        try:
            materialize(db, output_dir, days, cfg)
            if rows:
                aggregate(db, cfg, min(r["ts"] for r in rows)-cfg["max_interval_seconds"])
            if cfg.get("upload_enabled"):
                result["delivered"] = deliver(db, cfg)
            else:
                result["delivery"] = "local_only"
                with db:
                    db.executemany("UPDATE events SET materialized=1 WHERE id=?", [(row["id"],) for row in rows])
            maintain(db, output_dir, cfg, local_only=local_only)
        except Exception as exc:
            errors.append(type(exc).__name__)
        result.update(report(db, cfg))
        if local_only:
            result["retained_local_events"] = db.execute("SELECT count(*) FROM events").fetchone()[0]
            result["pending_events"] = 0
        if errors:
            result.update(status="degraded", errors=sorted(set(errors)))
        # Restart a hung native collector, but never on normal sleep with no worker runs.
        age = result.get("capture_age_seconds")
        startup_age = time.time() - (state/"mac-capture").stat().st_mtime if (state/"mac-capture").exists() else 0
        if (age is None and startup_age > cfg["stale_seconds"]) or (age is not None and age > cfg["stale_seconds"]):
            label = os.environ.get("MAC_CAPTURE_LABEL", "com.obsidian-agent.mac-capture")
            try:
                p = subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"], capture_output=True, timeout=10)
                result["collector_restart_requested"] = p.returncode == 0
            except subprocess.TimeoutExpired:
                result["collector_restart_requested"] = "outcome_unknown"
        result["spool_files"] = len(list((state/"outbox").glob("*.json")))
        if result["spool_files"] >= cfg["spool_warning_files"]:
            result["status"] = "degraded"
        atomic_json(state/"status.json", result)
        try:
            if cfg.get("upload_enabled"):
                atomic_json(Path(VAULT_PATH)/".sync/mac_capture_status.json", result)
        except OSError:
            result["vault_status_unavailable"] = True
    lock.close()
    return result


if __name__ == "__main__":
    print(json.dumps(run()))
