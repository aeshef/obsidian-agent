"""Persisted read-only condition checks, leases, checkpoints and bounded retries."""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .config import config
from .db import connection
from .memory import now, timestamp


def later(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest()


def create(ctx, registry, objective, tool_name, args, condition, expected, next_check, expires_at, project_id=""):
    cfg = config()
    if not objective.strip() or len(objective) + len(expected) + len(json.dumps(args)) > cfg["text_max_chars"]:
        raise ValueError("invalid_followup_size")
    if tool_name not in cfg["background_tools"] or not registry.has(tool_name):
        raise ValueError("background_tool_not_allowed")
    t = registry.get(tool_name)
    if not t.read_only:
        raise ValueError("background_requires_explicit_read_only")
    if condition not in ("nonempty", "contains", "json_equals", "changed"):
        raise ValueError("invalid_condition")
    if condition == "contains" and not expected:
        raise ValueError("expected_required")
    if condition == "json_equals":
        value = json.loads(expected)
        if not isinstance(value, dict) or not value:
            raise ValueError("expected_object_required")
    due = timestamp(next_check)
    expiry = timestamp(expires_at)
    if not due or not expiry or expiry <= due or expiry <= now():
        raise ValueError("future_expiry_and_check_required")
    import inspect

    inspect.signature(t.handler).bind(ctx=ctx, **args)
    payload = json.dumps(args, sort_keys=True, ensure_ascii=False)
    rid = uuid4().hex
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT id,status FROM agent_followups WHERE user_id=? AND objective=? AND tool=? AND args=?",
            (ctx.user_id, objective, tool_name, payload),
        ).fetchone()
        if existing:
            return dict(existing)
        if (
            project_id
            and not db.execute(
                "SELECT 1 FROM agent_projects WHERE user_id=? AND id=?", (ctx.user_id, project_id)
            ).fetchone()
        ):
            raise ValueError("unknown_project")
        count = db.execute(
            "SELECT count(*) FROM agent_followups WHERE user_id=? AND status IN ('waiting','running','paused')",
            (ctx.user_id,),
        ).fetchone()[0]
        if count >= cfg["max_open_followups"]:
            raise ValueError("followup_limit")
        db.execute(
            "INSERT INTO agent_followups VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid,
                ctx.user_id,
                ctx.domain,
                project_id,
                objective,
                tool_name,
                payload,
                condition,
                expected,
                "",
                "waiting",
                due,
                expiry,
                "",
                0,
                "",
                "none",
                now(),
            ),
        )
    return {"id": rid, "status": "waiting"}


def list_jobs(user_id):
    with connection() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT * FROM agent_followups WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, config()["max_open_followups"]),
            )
        ]


def update(user_id, rid, action):
    states = {"pause": "paused", "resume": "waiting", "cancel": "cancelled"}
    if action not in states:
        raise ValueError("invalid_action")
    with connection() as db:
        return (
            db.execute(
                "UPDATE agent_followups SET status=?,next_check=?,lease_until='',notify_state='none',failures=0,updated_at=? WHERE user_id=? AND id=? AND status IN ('waiting','running','paused','failed')",
                (states[action], now(), now(), user_id, rid),
            ).rowcount
            == 1
        )


def matched(job, output):
    condition = job["condition"]
    if condition == "nonempty":
        return bool(output.strip()) and output.strip() not in ("null", "[]", "{}")
    if condition == "contains":
        return job["expected"] in output
    if condition == "changed":
        return bool(job["baseline"]) and fingerprint(output) != job["baseline"]
    data = json.loads(output)
    expected = json.loads(job["expected"])
    return isinstance(data, dict) and all(k in data and data[k] == v for k, v in expected.items())


async def tick(app, notify):
    cfg = config()
    registry = app.merged_registry()
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE agent_followups SET status='waiting',lease_until='' WHERE status='running' AND lease_until<?",
            (now(),),
        )
        rows = db.execute(
            "SELECT * FROM agent_followups WHERE status='waiting' AND next_check<=? ORDER BY next_check LIMIT ?",
            (now(), cfg["worker_batch_size"]),
        ).fetchall()
        jobs = [dict(r) for r in rows]
        for j in jobs:
            db.execute(
                "UPDATE agent_followups SET status='running',lease_until=? WHERE id=?",
                (later(cfg["lease_seconds"]), j["id"]),
            )
    for job in jobs:
        status = "waiting"
        output = ""
        failures = job["failures"]
        baseline = job["baseline"]
        try:
            if job["expires_at"] <= now():
                status = "expired"
            else:
                if (
                    job["tool"] not in cfg["background_tools"]
                    or not registry.has(job["tool"])
                    or not registry.get(job["tool"]).read_only
                ):
                    raise ValueError("tool_unavailable")
                from shared.agent.types import AgentContext

                extras = {}
                for adapter in app._adapters.values():
                    extras.update(await adapter.prepare_extras(job["user_id"]))
                ctx = AgentContext(job["user_id"], job["domain"], job["objective"], "", extras=extras)
                result = await asyncio.wait_for(
                    registry.get(job["tool"]).handler(ctx=ctx, **json.loads(job["args"])),
                    timeout=cfg["probe_timeout_seconds"],
                )
                output = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                if matched(job, output):
                    status = "completed"
                baseline = fingerprint(output)
                failures = 0
        except Exception as exc:  # noqa: BLE001 — persist failure at the tool boundary
            failures += 1
            output = type(exc).__name__
            if failures >= cfg["max_probe_failures"]:
                status = "failed"
        with connection() as db:
            # A concurrent cancellation/pause wins over an in-flight check.
            db.execute(
                "UPDATE agent_followups SET status=?,baseline=?,failures=?,result=?,next_check=?,lease_until='',notify_state=?,updated_at=? WHERE id=? AND status='running'",
                (
                    status,
                    baseline,
                    failures,
                    output,
                    later(cfg["poll_min_seconds"]),
                    "pending" if status in ("completed", "failed", "expired") else "none",
                    now(),
                    job["id"],
                ),
            )
    await deliver(notify)


async def deliver(notify):
    # At-most-once notification attempt: a crash cannot produce repeated alerts.
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM agent_followups WHERE notify_state='pending' LIMIT ?", (config()["worker_batch_size"],)
            )
        ]
        for r in rows:
            db.execute("UPDATE agent_followups SET notify_state='sending' WHERE id=?", (r["id"],))
    for row in rows:
        state = "sent"
        try:
            await notify(row)
        except Exception:  # noqa: BLE001 — delivery can fail after Telegram accepted it
            state = "delivery_unknown"
        with connection() as db:
            db.execute("UPDATE agent_followups SET notify_state=? WHERE id=?", (state, row["id"]))
