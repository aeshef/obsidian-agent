"""Searchable episodes, versioned project facts, decisions and procedural notes."""

import json
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .config import config
from .db import connection


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def timestamp(value):
    if not value:
        return ""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone_required")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def archive(user_id, domain, role, content):
    if role not in ("user", "assistant") or not content:
        return
    cfg = config()
    cut = (datetime.now(timezone.utc) - timedelta(days=cfg["history_retention_days"])).isoformat()
    with connection() as db:
        db.execute(
            "INSERT INTO agent_episodes(user_id,domain,role,content,created_at) VALUES(?,?,?,?,?)",
            (user_id, domain, role, content, now()),
        )
        db.execute("DELETE FROM agent_episodes WHERE user_id=? AND created_at<?", (user_id, cut))
        db.execute(
            "DELETE FROM agent_episodes WHERE user_id=? AND id NOT IN (SELECT id FROM agent_episodes WHERE user_id=? ORDER BY id DESC LIMIT ?)",
            (user_id, user_id, cfg["history_max_rows_per_user"]),
        )


def search(user_id, query, limit=None):
    terms = re.findall(r"\w+", query, flags=re.UNICODE)
    if not terms:
        return []
    expression = " OR ".join('"' + t + '"' for t in terms[: config()["search_limit"]])
    with connection() as db:
        rows = db.execute(
            "SELECT e.* FROM agent_episodes_fts f JOIN agent_episodes e ON e.id=f.rowid WHERE agent_episodes_fts MATCH ? AND e.user_id=? ORDER BY bm25(agent_episodes_fts), e.id DESC LIMIT ?",
            (expression, user_id, min(limit or config()["search_limit"], config()["search_limit"])),
        ).fetchall()
        return [dict(r) for r in rows]


def project(user_id, name, summary, links):
    if not name.strip() or len(summary) > config()["text_max_chars"]:
        raise ValueError("invalid_project")
    with connection() as db:
        db.execute(
            "INSERT INTO agent_projects VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET summary=excluded.summary,links=excluded.links,updated_at=excluded.updated_at",
            (uuid4().hex, user_id, name.strip(), summary, json.dumps(links, ensure_ascii=False), now()),
        )
        row = dict(
            db.execute("SELECT * FROM agent_projects WHERE user_id=? AND name=?", (user_id, name.strip())).fetchone()
        )
        db.execute(
            "INSERT INTO agent_project_focus VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET project_id=excluded.project_id,updated_at=excluded.updated_at",
            (user_id, row["id"], now()),
        )
        return row


def projects(user_id):
    with connection() as db:
        return [
            dict(r)
            for r in db.execute("SELECT * FROM agent_projects WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
        ]


def record(
    user_id, kind, body, source, certainty="hypothesis", project_id="", valid_from="", valid_until="", supersedes=""
):
    if kind not in ("fact", "decision", "procedure", "preference"):
        raise ValueError("invalid_kind")
    if certainty not in ("user_stated", "observed", "hypothesis"):
        raise ValueError("invalid_certainty")
    if not source.strip() or not body.strip() or len(body) > config()["text_max_chars"]:
        raise ValueError("source_and_bounded_body_required")
    start = timestamp(valid_from) or now()
    end = timestamp(valid_until)
    if end and end <= start:
        raise ValueError("invalid_validity_range")
    rid = uuid4().hex
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if (
            project_id
            and not db.execute(
                "SELECT 1 FROM agent_projects WHERE user_id=? AND id=?", (user_id, project_id)
            ).fetchone()
        ):
            raise ValueError("unknown_project")
        if supersedes and kind == "procedure":
            raise ValueError("procedure_supersession_requires_new_review")
        if supersedes:
            changed = db.execute(
                "UPDATE agent_records SET status='superseded' WHERE user_id=? AND id=? AND status='active'",
                (user_id, supersedes),
            ).rowcount
            if not changed:
                raise ValueError("unknown_or_superseded_record")
        # Procedures remain proposals until explicit approval; never edit prompts.
        status = "proposed" if kind == "procedure" else "active"
        db.execute(
            "INSERT INTO agent_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, user_id, kind, project_id, body, source, certainty, status, start, end, supersedes, now()),
        )
        return {"id": rid, "status": status}


def records(user_id, project_id="", include_history=False):
    with connection() as db:
        sql = "SELECT * FROM agent_records WHERE user_id=?"
        args = [user_id]
        if project_id:
            sql += " AND project_id=?"
            args.append(project_id)
        if not include_history:
            sql += " AND status='active' AND valid_from<=? AND (valid_until='' OR valid_until>?)"
            args.extend([now(), now()])
        return [dict(r) for r in db.execute(sql + " ORDER BY created_at DESC", args)]


def review_record(user_id, record_id, approve):
    with connection() as db:
        return (
            db.execute(
                "UPDATE agent_records SET status=? WHERE user_id=? AND id=? AND status='proposed'",
                ("active" if approve else "rejected", user_id, record_id),
            ).rowcount
            == 1
        )
