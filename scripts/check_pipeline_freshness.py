"""Report source age and degraded pipelines separately from transport success."""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from planning_bot.services.calendar_bridge import config


def source_status(captured: str | None, threshold: int, now: datetime) -> dict:
    if not captured:
        return {"status": "missing"}
    try:
        ts = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=now.tzinfo)
        age = (now - ts).total_seconds()
        return {"status": "invalid_clock" if age < -300 else "stale" if age > threshold else "ok",
                "captured_at": captured, "age_seconds": round(age)}
    except ValueError:
        return {"status": "invalid_timestamp"}


def run() -> dict:
    from planning_bot.core.config import CALENDAR_JSON_FILE, IPHONE_CONTEXT_DIR, VAULT_PATH
    cfg = config()
    tz = ZoneInfo(os.environ.get("TIMEZONE") or "UTC")
    now = datetime.now(tz)
    from planning_bot.services.iphone_snapshot_names import parse_filename_ts
    stamps = [parse_filename_ts(p.name) for p in Path(IPHONE_CONTEXT_DIR).glob("*.txt")]
    stamps = [s for s in stamps if s is not None]
    latest = max(stamps).isoformat() if stamps else None
    from planning_bot.tools.iphone_mail_sync import _parse_body
    captures = []
    for path in Path(IPHONE_CONTEXT_DIR).glob("*.txt"):
        try:
            row = _parse_body(path.read_text()) or {}
            if row.get("captured_at"):
                captures.append(datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00")))
        except (OSError, ValueError, TypeError):
            continue
    if captures:
        latest = max(captures).isoformat()
    meta = json.loads(CALENDAR_JSON_FILE.read_text()).get("meta", {}) if CALENDAR_JSON_FILE.exists() else {}
    from shared.capabilities.profile import get_capabilities
    profile = get_capabilities()
    report = {"checked_at": now.isoformat(), "sources": {}}
    if profile.connector("apple_health"):
        report["sources"]["iphone"] = source_status(latest, cfg["iphone_stale_seconds"], now)
    if profile.connector("apple_calendar"):
        report["sources"]["calendar"] = source_status(meta.get("source_captured_at") or meta.get("txt_last_parsed"), cfg["stale_seconds"], now)
    if profile.connector("mac_context"):
        from planning_bot.services.mac_capture import config as mac_config
        mac_cfg = mac_config()
        if mac_cfg.get("enabled"):
            mac_path = Path(VAULT_PATH)/".sync/mac_capture_status.json"
            local_only = not mac_cfg.get("upload_enabled")
            if local_only and sys.platform == "darwin":
                mac_path = Path(os.environ.get("MAC_CAPTURE_STATE", str(Path.home()/"Library/Application Support/obsidian-agent/mac-capture"))) / "status.json"
            mac = json.loads(mac_path.read_text()) if mac_path.exists() else {}
            report["sources"]["mac"] = source_status(mac.get("last_capture"), mac_cfg["stale_seconds"], now)
            report["sources"]["mac"]["delivery"] = "local_only" if local_only else "server"
            if local_only and sys.platform != "darwin":
                report["sources"]["mac"]["status"] = "not_applicable"
            elif not local_only:
                report["sources"]["mac"]["pending_events"] = mac.get("pending_events")
            if mac.get("status") == "degraded":
                report["sources"]["mac"]["status"] = "degraded"
    from shared.capabilities.finance_gates import broker_sync_enabled
    if broker_sync_enabled():
        import sqlite3
        from finance_bot.bot.finance_db_paths import resolve_vault_replica_db
        path = resolve_vault_replica_db(Path(VAULT_PATH))
        stamp = None
        if path and path.is_file():
            try:
                with sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True) as db:
                    stamp = db.execute("SELECT max(snapshot_date) FROM account_balance_snapshots").fetchone()[0]
            except sqlite3.Error:
                pass
        from shared.finance.broker_sync_config import load_broker_sync_yaml
        broker_cfg = load_broker_sync_yaml()
        report["sources"]["broker"] = source_status(stamp, broker_cfg["stale_seconds"], now)
    from shared import llm_payment_guard
    from shared.constants import deepseek_chat_completions_url, llm_api_key
    payment = llm_payment_guard._state(deepseek_chat_completions_url(), llm_api_key())
    if payment.exists():
        report["dependencies"] = {"llm": {"status": "payment_required"}}
    report["status"] = "ok" if all(s["status"] in {"ok", "not_applicable"} for s in report["sources"].values()) else "degraded"
    queue_path = Path(VAULT_PATH)/".sync/health_queue_bridge.json"
    if sys.platform == "darwin" and queue_path.exists():
        try:
            queue = json.loads(queue_path.read_text())
            if queue.get("status") == "degraded":
                report.setdefault("dependencies", {})["health_queue"] = queue
        except (OSError, ValueError):
            report.setdefault("dependencies", {})["health_queue"] = {"status": "invalid"}
    if report.get("dependencies"):
        report["status"] = "degraded"
    state = Path(VAULT_PATH) / ".sync"
    worker_path = state / "calendar_bridge_status.json"
    if cfg.get("enabled") and profile.connector("apple_calendar") and sys.platform == "darwin":
        worker = json.loads(worker_path.read_text()) if worker_path.exists() else {}
        report["calendar_worker"] = worker.get("status", "missing")
        if report["calendar_worker"] != "ok":
            report["status"] = "degraded"
    if "iphone" in report["sources"]:
        from planning_bot.services.health_coverage import health_coverage
        report["health_coverage"] = health_coverage()
    from shared.obsidian_ui.freshness import dataset_status
    report['dashboards'] = dataset_status(Path(VAULT_PATH), now)
    if any(item['status'] != 'ok' for item in report['dashboards'].values()):
        report['status'] = 'degraded'
    state.mkdir(parents=True, exist_ok=True)
    target = state / "pipeline_health.json"
    temp = target.with_suffix(".tmp"); temp.write_text(json.dumps(report, ensure_ascii=False)); temp.replace(target)
    health = state / "health_report.md"
    if health.exists():
        body = health.read_text().split("\n## Source freshness")[0]
        body += "\n## Source freshness\n\n"
        for name, status in report["sources"].items():
            body += f"- {name}: {status['status']}; captured={status.get('captured_at', 'unknown')}\n"
        if "calendar_worker" in report:
            body += f"- calendar_worker: {report['calendar_worker']}\n"
        health.write_text(body)
    return report


if __name__ == "__main__":
    print(json.dumps(run()))
