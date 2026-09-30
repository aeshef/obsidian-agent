"""Durable mutation receipts. Unknown effects are never blindly replayed."""

import hashlib
import json
from uuid import uuid4

from .db import connection
from .memory import now


def begin(user_id, request_key, tool, args):
    digest = hashlib.sha256(json.dumps(args, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM agent_operations WHERE user_id=? AND request_key=? AND tool=? AND args_hash=?",
            (user_id, request_key, tool, digest),
        ).fetchone()
        if row:
            return dict(row), False
        op = uuid4().hex
        db.execute(
            "INSERT INTO agent_operations VALUES(?,?,?,?,?,?,?,?,?)",
            (op, user_id, request_key, tool, digest, "running", "", now(), now()),
        )
        return {"id": op, "status": "running", "result": ""}, True


def finish(user_id, op, status, result):
    if status not in ("verified", "pending", "unverified", "outcome_unknown", "rejected"):
        raise ValueError("invalid_receipt_status")
    with connection() as db:
        db.execute(
            "UPDATE agent_operations SET status=?,result=?,updated_at=? WHERE user_id=? AND id=?",
            (status, result, now(), user_id, op),
        )


def read(user_id, op):
    with connection() as db:
        row = db.execute(
            "SELECT id,tool,status,result,created_at,updated_at FROM agent_operations WHERE user_id=? AND id=?",
            (user_id, op),
        ).fetchone()
        return dict(row) if row else None


async def execute(tool, tc, ctx):
    def receipt(value):
        ctx.extras.setdefault("operation_receipts", []).append(value)
        return json.dumps(value, ensure_ascii=False)

    key = ctx.extras.setdefault("request_key", uuid4().hex)
    row, fresh = begin(ctx.user_id, key, tc.name, tc.arguments)
    if not fresh:
        return receipt(
            {
                "operation_id": row["id"],
                "status": row["status"] if row["status"] != "running" else "outcome_unknown",
                "replayed": True,
                "result": row["result"],
            }
        )
    try:
        result = await tool.handler(**tc.arguments, ctx=ctx)
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        status = "unverified"
        if tool.verifier:
            status = await tool.verifier(ctx, tc.arguments, result)
        finish(ctx.user_id, row["id"], status, content)
    except Exception as exc:  # noqa: BLE001 — persist failure at the tool boundary
        finish(ctx.user_id, row["id"], "outcome_unknown", type(exc).__name__)
        return receipt({"operation_id": row["id"], "status": "outcome_unknown", "error": type(exc).__name__})
    except BaseException:
        finish(ctx.user_id, row["id"], "outcome_unknown", "")
        raise
    return receipt({"operation_id": row["id"], "status": status, "result": result})


def guard_answer(ctx, answer):
    uncertain = [
        r["operation_id"] for r in ctx.extras.get("operation_receipts", []) if r["status"] == "outcome_unknown"
    ]
    if not uncertain:
        return answer
    from shared.i18n import msgf

    return msgf("agent", "operation_unknown", ids=", ".join(dict.fromkeys(uncertain)))
