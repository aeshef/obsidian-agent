from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("kb.query.history")


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def history_path(user_id: int) -> Path:
    d = _package_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"query_history_{user_id}.json"


def load_history(user_id: int, *, max_turns: int = 6) -> list[dict[str, Any]]:
    p = history_path(user_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        log.warning("bad query history file, resetting")
        return []
    if not isinstance(data, list):
        return []
    return data[-max_turns:]


def append_turn(user_id: int, question: str, answer: str, *, max_turns: int = 6) -> None:
    cur = load_history(user_id, max_turns=999)
    cur.append({"q": question, "a": answer})
    cur = cur[-max_turns:]
    p = history_path(user_id)
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=0), encoding="utf-8")


def format_history_for_prompt(hist: list[dict[str, Any]]) -> str:
    if not hist:
        return ""
    lines: list[str] = []
    for i, turn in enumerate(hist, 1):
        q = turn.get("q") or ""
        a = (turn.get("a") or "")[:2000]
        from shared.domain_messages import dmsg

        lines.append(
            dmsg("knowledge_brain_query", "history_turn", index=i, question=q, answer=a)
        )
    return "\n\n".join(lines)
