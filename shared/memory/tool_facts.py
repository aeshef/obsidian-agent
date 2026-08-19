"""Prior-turn tool excerpts for the system prompt (not Telegram)."""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from pathlib import Path

from shared.agent.types import AgentContext, AgentMessage

log = logging.getLogger("shared.memory.tool_facts")

_lock = threading.Lock()
_store: dict[tuple[int, str], str] = {}
_sqlite_ready = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_facts (
  user_id INTEGER NOT NULL,
  domain TEXT NOT NULL,
  facts TEXT NOT NULL,
  PRIMARY KEY (user_id, domain)
);
"""


def _persist_enabled() -> bool:
    raw = (os.environ.get("MEMORY_SESSION_PERSIST") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _db_path() -> Path:
    raw = os.environ.get("AGENT_MEMORY_DB", "").strip()
    return Path(raw) if raw else Path("memory.db")


def _ensure_sqlite() -> None:
    global _sqlite_ready
    if _sqlite_ready or not _persist_enabled():
        return
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    _sqlite_ready = True


def _key(user_id: int, domain: str) -> tuple[int, str]:
    return (int(user_id), str(domain or "general"))


def set_tool_facts(user_id: int, domain: str, facts: str) -> None:
    body = (facts or "").strip()
    k = _key(user_id, domain)
    with _lock:
        if body:
            _store[k] = body
        else:
            _store.pop(k, None)
    if not _persist_enabled():
        return
    _ensure_sqlite()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            if body:
                conn.execute(
                    "INSERT INTO tool_facts(user_id, domain, facts) VALUES(?,?,?) "
                    "ON CONFLICT(user_id, domain) DO UPDATE SET facts=excluded.facts",
                    (k[0], k[1], body),
                )
            else:
                conn.execute(
                    "DELETE FROM tool_facts WHERE user_id=? AND domain=?",
                    (k[0], k[1]),
                )
            conn.commit()
    except sqlite3.Error as e:
        log.warning("tool_facts sqlite write failed: %s", e)


def get_tool_facts(user_id: int, domain: str) -> str:
    k = _key(user_id, domain)
    with _lock:
        if k in _store:
            return _store[k]
    if not _persist_enabled():
        return ""
    _ensure_sqlite()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            row = conn.execute(
                "SELECT facts FROM tool_facts WHERE user_id=? AND domain=?",
                (k[0], k[1]),
            ).fetchone()
        if row and row[0]:
            text = str(row[0])
            with _lock:
                _store[k] = text
            return text
    except sqlite3.Error as e:
        log.warning("tool_facts sqlite read failed: %s", e)
    return ""


def remember_loop_facts(user_id: int, domain: str, chunks: list[tuple[str, str]]) -> None:
    from shared.agent.platform_config import platform_int

    cap = platform_int("agent", "tool_facts_max_chars", default=0)
    parts: list[str] = []
    used = 0
    for name, body in chunks:
        text = (body or "").strip()
        if not text:
            continue
        block = f"{name}:\n{text}"
        if cap and used + len(block) + 2 > cap:
            remain = cap - used - 2
            if remain > 24:
                parts.append(block[: remain - 1].rstrip() + "…")
            break
        parts.append(block)
        used += len(block) + 2
    set_tool_facts(user_id, domain, "\n\n".join(parts))


class ToolFactsMemory:
    async def read(self, ctx: AgentContext) -> str:
        facts = get_tool_facts(ctx.user_id, ctx.domain)
        if not facts:
            return ""
        from shared.i18n import msgf

        return msgf("agent", "tool_facts_header", facts=facts)

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        return
