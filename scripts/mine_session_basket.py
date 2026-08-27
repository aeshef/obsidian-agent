#!/usr/bin/env python3
"""Mine a review basket from session SQLite and/or agent_traces (no PII in public gold).

Traces store no message bodies by design. Session messages appear only when
MEMORY_SESSION_PERSIST=1 and the bot wrote to AGENT_MEMORY_DB.

Prod bot usually writes on the VPS — use ``--ssh obsidian-server`` (or
``SYNC_SERVER_HOST``) to read ``/root/bots/memory.db`` remotely.

  PYTHONPATH=. ./scripts/oa-python.sh scripts/mine_session_basket.py
  PYTHONPATH=. ./scripts/oa-python.sh scripts/mine_session_basket.py --ssh obsidian-server
  PYTHONPATH=. ./scripts/oa-python.sh scripts/mine_session_basket.py --out eval/gold/local_basket.yaml

Output is gitignored (local_basket.yaml). Fill ``label:`` (good|bad|ok|skip) yourself.
Context-sensitive items are marked ``context_sensitive: true`` — expect drift.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_CONTEXTISH = re.compile(
    r"(?i)\b(вчерашн\w*|вчера|сегодня|завтра|this week|yesterday|today|"
    r"сейчас|в работе|WIP|закрой|эту задачу)\b"
)


def _db_path() -> Path:
    raw = (os.environ.get("AGENT_MEMORY_DB") or "").strip()
    return Path(raw) if raw else ROOT / "memory.db"


def _ssh_host(explicit: str) -> str:
    if (explicit or "").strip():
        return explicit.strip()
    env = (os.environ.get("SYNC_SERVER_HOST") or "").strip()
    # root@host → prefer SSH config alias when present
    if env.startswith("root@") and Path.home().joinpath(".ssh/config").is_file():
        return "obsidian-server"
    return env or ""


def _fetch_remote_db(ssh_host: str, remote_path: str) -> Path:
    dest = Path(tempfile.mkstemp(prefix="oa_memory_", suffix=".db")[1])
    cmd = ["scp", "-o", "BatchMode=yes", f"{ssh_host}:{remote_path}", str(dest)]
    subprocess.check_call(cmd)
    return dest


def _mine_sessions(db: Path, *, limit: int, source: str = "session") -> list[dict]:
    if not db.is_file():
        return []
    conn = sqlite3.connect(str(db))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "session_messages" not in tables:
            return []
        rows = conn.execute(
            """
            SELECT id, domain, role, content, ts FROM session_messages
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    messages = [
        {
            "id": sid,
            "domain": domain,
            "role": role,
            "content": content or "",
            "ts": ts,
        }
        for sid, domain, role, content, ts in rows
    ]
    user_idxs = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if limit > 0:
        user_idxs = user_idxs[-limit:]

    out: list[dict] = []
    seen: set[str] = set()
    for i in user_idxs:
        m = messages[i]
        text = (m["content"] or "").strip()
        if len(text) < 3 or text in seen:
            continue
        seen.add(text)

        answer = None
        answer_ts = None
        for j in range(i + 1, len(messages)):
            if messages[j]["domain"] != m["domain"]:
                continue
            if messages[j]["role"] == "assistant":
                answer = messages[j]["content"]
                answer_ts = messages[j]["ts"]
                break
            if messages[j]["role"] == "user":
                break

        prior: list[dict] = []
        for j in range(i - 1, -1, -1):
            if messages[j]["domain"] != m["domain"]:
                continue
            prior.append(messages[j])
            if len(prior) >= 4:
                break
        prior.reverse()
        dialogue = [
            {"role": p["role"], "ts": p["ts"], "text": (p["content"] or "")[:2000]}
            for p in prior
        ]
        dialogue.append({"role": "user", "ts": m["ts"], "text": text[:2000]})
        if answer is not None:
            dialogue.append(
                {"role": "assistant", "ts": answer_ts, "text": (answer or "")[:4000]}
            )

        out.append(
            {
                "id": f"{source}-{m['id']}",
                "source": source,
                "domain": m["domain"],
                "ts": m["ts"],
                "question": text[:800],
                "answer": (answer or "")[:4000] if answer is not None else None,
                "answered": answer is not None,
                "dialogue": dialogue,
                "context_sensitive": bool(_CONTEXTISH.search(text)),
                "label": "pending",
                "notes": ""
                if answer is not None
                else "no assistant reply stored after this user turn",
            }
        )
    return out


def _mine_traces(path: Path, *, limit: int) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rows = rows[-limit:]
    tools = Counter()
    for r in rows:
        for t in r.get("selected_tools") or []:
            tools[t] += 1
    templates = {
        "get_activity_events": "How many tasks did I close yesterday? List unique completions.",
        "get_action_log": "Summarize my task action log for yesterday.",
        "get_kanban": "What is currently in progress on my board?",
        "get_transactions": "How much did I spend last week by category?",
        "search_knowledge_base": "Find notes about onboarding in my knowledge base.",
        "get_calendar": "What is on my calendar for today?",
        "get_balance": "What is my current balance?",
    }
    out: list[dict] = []
    for tool, _n in tools.most_common(12):
        q = templates.get(tool)
        if not q:
            continue
        out.append(
            {
                "id": f"trace-pattern-{tool}",
                "source": "trace_pattern",
                "domain": "unified",
                "question": q,
                "suggested_tools": [tool],
                "context_sensitive": tool
                in {"get_activity_events", "get_action_log", "get_kanban", "get_calendar"},
                "label": "pending",
                "notes": "Synthesized from trace tool frequency; not a real utterance.",
            }
        )
    out.append(
        {
            "id": "trace-meta",
            "source": "trace_meta",
            "domain": "ops",
            "question": "(meta) review end_reason / tool_clip_ratio after deploy",
            "trace_summary": {
                "n": len(rows),
                "end_reasons": dict(Counter(r.get("end_reason") for r in rows)),
                "top_tools": tools.most_common(10),
            },
            "label": "skip",
            "notes": "Ops checklist, not an agent prompt.",
        }
    )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "gold" / "local_basket.yaml")
    ap.add_argument("--session-limit", type=int, default=80)
    ap.add_argument("--trace-limit", type=int, default=200)
    ap.add_argument("--traces", type=Path, default=ROOT / "logs" / "agent_traces.jsonl")
    ap.add_argument(
        "--ssh",
        nargs="?",
        const="obsidian-server",
        default="",
        help="SCP memory.db from host (default alias: obsidian-server)",
    )
    ap.add_argument(
        "--remote-db",
        default="/root/bots/memory.db",
        help="Remote path when using --ssh",
    )
    ap.add_argument(
        "--with-trace-patterns",
        action="store_true",
        help="Also append synthetic prompts from local agent_traces.jsonl",
    )
    args = ap.parse_args(argv)

    tmp: Path | None = None
    source = "session"
    try:
        host = _ssh_host(args.ssh)
        if host:
            tmp = _fetch_remote_db(host, args.remote_db)
            db = tmp
            source = "server_session"
            print(f"fetched {host}:{args.remote_db} -> {db}")
        else:
            db = _db_path()
        items = _mine_sessions(db, limit=args.session_limit, source=source)
        if args.with_trace_patterns or not items:
            items.extend(_mine_traces(args.traces, limit=args.trace_limit))
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    doc = {
        "version": 2,
        "instruction": (
            "Score the assistant turn: label=good|bad|ok|skip. "
            "Use dialogue[] for follow-ups; answer may be null if missing in DB."
        ),
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    n_sess = sum(1 for i in items if str(i.get("source", "")).endswith("session"))
    n_ans = sum(1 for i in items if i.get("answered"))
    print(f"wrote {args.out} items={len(items)} (session={n_sess}, answered={n_ans})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
