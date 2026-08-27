#!/usr/bin/env python3
"""Mine a review basket from session SQLite and/or agent_traces (no PII in public gold).

Traces store no message bodies by design. Session messages appear only when
MEMORY_SESSION_PERSIST=1 and the bot wrote to AGENT_MEMORY_DB.

  PYTHONPATH=. ./scripts/oa-python.sh scripts/mine_session_basket.py
  PYTHONPATH=. ./scripts/oa-python.sh scripts/mine_session_basket.py --out eval/gold/local_basket.yaml

Output is gitignored (local_basket.yaml). Fill ``label:`` (good|bad|ok|skip) yourself.
Context-sensitive items are marked ``context_sensitive: true`` — expect drift.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_CONTEXTISH = re.compile(
    r"(?i)\b(вчера|сегодня|завтра|this week|yesterday|today|сейчас|в работе|WIP)\b"
)


def _db_path() -> Path:
    import os

    raw = (os.environ.get("AGENT_MEMORY_DB") or "").strip()
    return Path(raw) if raw else ROOT / "memory.db"


def _mine_sessions(db: Path, *, limit: int) -> list[dict]:
    if not db.is_file():
        return []
    conn = sqlite3.connect(str(db))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "session_messages" not in tables:
            return []
        rows = conn.execute(
            """
            SELECT domain, role, content, ts FROM session_messages
            WHERE role='user'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    out: list[dict] = []
    for domain, _role, content, ts in rows:
        text = (content or "").strip()
        if len(text) < 8:
            continue
        out.append(
            {
                "id": f"session-{ts}-{len(out)}",
                "source": "session",
                "domain": domain,
                "question": text[:500],
                "ts": ts,
                "context_sensitive": bool(_CONTEXTISH.search(text)),
                "label": "pending",
                "notes": "",
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
    # Synthetic prompts by dominant tool clusters (OSS-safe, no user text).
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
    args = ap.parse_args(argv)

    items = _mine_sessions(_db_path(), limit=args.session_limit)
    items.extend(_mine_traces(args.traces, limit=args.trace_limit))
    doc = {
        "version": 1,
        "instruction": (
            "Set label to good|bad|ok|skip. Context-sensitive rows need a frozen "
            "expected_facts block or will drift as the vault changes."
        ),
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"wrote {args.out} items={len(items)} (session={sum(1 for i in items if i.get('source')=='session')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
