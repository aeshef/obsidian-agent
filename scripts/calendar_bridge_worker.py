"""Mac worker: native Calendar snapshot and durable server request processing."""
from __future__ import annotations
import fcntl
import json
import os
import shlex
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from planning_bot.services.calendar_bridge import config


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False))
    os.chmod(temp, 0o600)
    temp.replace(path)


def native(request: dict) -> dict:
    helper = os.environ.get("CALENDAR_EVENTKIT_HELPER", str(Path.home() / "Applications/Obsidian Calendar Bridge.app/Contents/MacOS/calendar-eventkit"))
    try:
        # LaunchServices gives the app its own stable Calendar privacy identity,
        # independent of whether the caller is Terminal, Codex, or launchd.
        with tempfile.TemporaryDirectory(prefix="calendar-native-") as folder:
            src, out = Path(folder) / "request.json", Path(folder) / "result.json"
            src.write_text(json.dumps(request)); os.chmod(src, 0o600)
            subprocess.run(["/usr/bin/open", "-W", "-n", str(Path(helper).parents[2]),
                            "--args", "--request", str(src), "--output", str(out)],
                           text=True, capture_output=True, check=False, timeout=config()["native_timeout_seconds"])
            # A short-lived app may finish before `open -W` attaches to its PID.
            # Its atomic result is authoritative even if LaunchServices exits nonzero.
            if out.exists():
                return json.loads(out.read_text())
            return {"status": "outcome_unknown", "error": "native_result_missing"}
    except subprocess.TimeoutExpired:
        return {"status": "outcome_unknown", "error": "native_timeout"}
    except Exception as exc:
        return {"status": "failed", "error": type(exc).__name__}


def remote(request: dict) -> dict:
    root = os.environ["SERVER_BOTS"]
    command = f"cd {shlex.quote(root)} && ./scripts/oa-python.sh scripts/calendar_bridge_rpc.py"
    proc = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", os.environ["SERVER"], command],
                          input=json.dumps(request), text=True, capture_output=True, timeout=30)
    if proc.returncode:
        raise RuntimeError("calendar_rpc_failed")
    return json.loads(proc.stdout)


def run() -> dict:
    cfg = config()
    from shared.capabilities.profile import get_capabilities
    if not cfg.get("enabled") or not get_capabilities().connector("apple_calendar"):
        return {"status": "disabled"}
    from planning_bot.core.config import CALENDAR_JSON_FILE, VAULT_PATH
    state = Path(VAULT_PATH) / ".sync"
    state.mkdir(parents=True, exist_ok=True)
    lock = (state / "calendar_bridge.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {"status": "busy"}
    report = {"checked_at": datetime.now().astimezone().isoformat(), "status": "ok"}
    snapshot_path = CALENDAR_JSON_FILE.with_suffix(".snapshot.json")
    due = not snapshot_path.exists() or time.time() - snapshot_path.stat().st_mtime >= cfg["refresh_seconds"]
    try:
        if cfg.get("write_enabled"):
            probe = native({"action": "probe"})
            if probe.get("status") != "ready":
                raise RuntimeError(probe.get("error", "native_probe_failed"))
            item = remote({"action": "claim"}).get("request")
            if item:
                result = native({"action": "create", **item})
                remote({"action": "ack", "request_id": item["request_id"], "lease": item["lease"], "result": result})
                report["write_status"] = result["status"]
                if result["status"] != "created":
                    report["status"] = "degraded"
                due = due or result["status"] == "created"
        if due:
            tz = ZoneInfo(os.environ.get("CALENDAR_TZ") or os.environ.get("TIMEZONE") or "UTC")
            now = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
            snapshot = native({"action": "snapshot", "start": (now - timedelta(days=cfg["past_days"])).isoformat(),
                               "end": (now + timedelta(days=cfg["future_days"] + 1)).isoformat()})
            if snapshot.get("complete") is not True:
                raise RuntimeError(snapshot.get("error", "native_snapshot_failed"))
            # Validate the entire snapshot before replacing the last known good source.
            from planning_bot.services.calendar_snapshot import ingest
            ingest(snapshot, CALENDAR_JSON_FILE, str(tz))
            atomic_json(snapshot_path, snapshot)
        snapshot = json.loads(snapshot_path.read_text())
        local = json.loads(CALENDAR_JSON_FILE.read_text())
        labels = {(e.get('calendar_id'), e.get('native_id'), e.get('start_at')): e for e in local.get('events', [])}
        for row in snapshot['events']:
            label = labels.get((row.get('calendar_id'), row.get('native_id'), row.get('start_at')), {})
            if row.get('title') == label.get('title'):
                for key in ('activity_type', 'activity_sig'):
                    if key in label: row[key] = label[key]
        remote({"action": "snapshot", "snapshot": snapshot})
        report["source_captured_at"] = snapshot["captured_at"]
        remote({"action": "heartbeat", "report": report})
    except Exception as exc:
        report.update(status="error", error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
    finally:
        atomic_json(state / "calendar_bridge_status.json", report)
        lock.close()
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result))
    sys.exit(1 if result.get("status") == "error" else 0)
