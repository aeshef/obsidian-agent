"""Small task-specific evidence packets, with links to full persisted records."""

import json
import re

from . import memory
from .config import config, enabled
from .db import connection


def relevant(user_id, query):
    terms = set(re.findall(r"\w+", query.lower()))

    def score(text):
        return len(terms & set(re.findall(r"\w+", text.lower())))

    projects = memory.projects(user_id)
    ranked = sorted(projects, key=lambda p: score(p["name"] + " " + p["summary"]), reverse=True)
    selected = [p for p in ranked if score(p["name"] + " " + p["summary"])][: config()["search_limit"]]
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=config()["project_focus_seconds"])).isoformat(
        timespec="seconds"
    )
    with connection() as db:
        focus = db.execute(
            "SELECT project_id FROM agent_project_focus WHERE user_id=? AND updated_at>=?", (user_id, cutoff)
        ).fetchone()
    if not selected and focus:
        selected = [p for p in projects if p["id"] == focus["project_id"]]
    ids = {p["id"] for p in selected}
    records = [
        dict(r)
        for r in memory.records(user_id)
        if r["kind"] == "preference" or r["project_id"] in ids or score(r["body"])
    ]
    for record in records:
        record["source"] = record["source"][: config()["context_source_chars"]]
    with connection() as db:
        jobs = [
            dict(r)
            for r in db.execute(
                "SELECT id,objective,status,project_id,next_check FROM agent_followups WHERE user_id=? AND status IN ('waiting','running','paused','failed') ORDER BY updated_at DESC LIMIT ?",
                (user_id, config()["max_open_followups"]),
            )
        ]
    jobs = [j for j in jobs if j["project_id"] in ids or score(j["objective"])]
    return {
        "projects": selected,
        "records": records[: config()["search_limit"]],
        "open_followups": jobs[: config()["search_limit"]],
    }


class TaskContextMemory:
    async def read(self, ctx):
        if not enabled():
            return ""
        packet = relevant(ctx.user_id, ctx.question)
        cap = config()["context_max_chars"]
        # Drop whole items instead of truncating JSON/evidence mid-sentence.
        while len(json.dumps(packet, ensure_ascii=False)) > cap:
            key = max(packet, key=lambda k: len(json.dumps(packet[k], ensure_ascii=False)))
            if not packet[key]:
                break
            packet[key].pop()
        if not any(packet.values()):
            return ""
        return "<retrieved_context_data>\n" + json.dumps(packet, ensure_ascii=False) + "\n</retrieved_context_data>"

    async def write(self, ctx, turn):
        pass
