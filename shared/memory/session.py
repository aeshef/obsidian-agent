"""Layer 1: short dialogue history (in-memory + optional SQLite)."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque

from shared.agent.types import AgentContext, AgentMessage

log = logging.getLogger("shared.memory.session")

_store: dict[tuple[int, str], Deque[AgentMessage]] = {}
_sqlite_ready = False


def _persist_enabled() -> bool:
    return os.environ.get("MEMORY_SESSION_PERSIST", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _db_path() -> Path:
    raw = os.environ.get("AGENT_MEMORY_DB", "").strip()
    return Path(raw) if raw else Path("memory.db")


def _max_messages() -> int:
    try:
        turns = int(os.environ.get("AGENT_SESSION_MAX_TURNS", "4"))
        return max(2, turns * 2)
    except ValueError:
        return 8


def _ensure_sqlite() -> None:
    global _sqlite_ready
    if _sqlite_ready or not _persist_enabled():
        return
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_user_domain ON session_messages(user_id, domain)"
        )
        conn.commit()
    _sqlite_ready = True
    _migrate_planning_file_history(path)


def _migrate_planning_file_history(db_path: Path) -> None:
    """One-time import of planning chat_history.json into SQLite (if table empty)."""
    if os.environ.get("MEMORY_SESSION_MIGRATE_PLANNING", "1").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return
    try:
        from planning_bot.core.config import LOG_DIR

        hist_file = LOG_DIR / "chat_history.json"
        if not hist_file.exists():
            return
        with sqlite3.connect(str(db_path)) as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM session_messages WHERE domain='planning'"
            ).fetchone()[0]
            if n > 0:
                return
            with open(hist_file, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for chat_key, messages in data.items():
                if not str(chat_key).isdigit() or not isinstance(messages, list):
                    continue
                uid = int(chat_key)
                for m in messages[-_max_messages() :]:
                    if not isinstance(m, dict):
                        continue
                    role = m.get("role") or "user"
                    content = m.get("content") or ""
                    conn.execute(
                        "INSERT INTO session_messages (user_id, domain, role, content, ts) VALUES (?, ?, ?, ?, ?)",
                        (uid, "planning", role, content, now),
                    )
            conn.commit()
            log.info("migrated planning chat_history.json into session_messages")
    except Exception as e:
        log.debug("planning history migration skipped: %s", e)


def _load_sqlite(user_id: int, domain: str) -> list[AgentMessage]:
    _ensure_sqlite()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            rows = conn.execute(
                "SELECT role, content FROM session_messages WHERE user_id=? AND domain=? "
                "ORDER BY id DESC LIMIT ?",
                (user_id, domain, _max_messages()),
            ).fetchall()
        rows.reverse()
        return [AgentMessage(role=r[0], content=r[1]) for r in rows]
    except sqlite3.Error as e:
        log.warning("session sqlite read failed: %s", e)
        return []


def _append_sqlite(user_id: int, domain: str, role: str, content: str) -> None:
    _ensure_sqlite()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            conn.execute(
                "INSERT INTO session_messages (user_id, domain, role, content, ts) VALUES (?, ?, ?, ?, ?)",
                (user_id, domain, role, content, now),
            )
            # prune old
            conn.execute(
                """
                DELETE FROM session_messages WHERE id NOT IN (
                    SELECT id FROM session_messages
                    WHERE user_id=? AND domain=?
                    ORDER BY id DESC LIMIT ?
                ) AND user_id=? AND domain=?
                """,
                (user_id, domain, _max_messages(), user_id, domain),
            )
            conn.commit()
    except sqlite3.Error as e:
        log.warning("session sqlite append failed: %s", e)


def _clear_sqlite(user_id: int, domain: str) -> None:
    if not _persist_enabled():
        return
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            conn.execute(
                "DELETE FROM session_messages WHERE user_id=? AND domain=?",
                (user_id, domain),
            )
            conn.commit()
    except sqlite3.Error as e:
        log.warning("session sqlite clear failed: %s", e)


def get_history(user_id: int, domain: str) -> list[AgentMessage]:
    key = (user_id, domain)
    if key in _store:
        return list(_store[key])
    if _persist_enabled():
        msgs = _load_sqlite(user_id, domain)
        if msgs:
            _store[key] = deque(msgs, maxlen=_max_messages())
            return list(_store[key])
    return []


def append_turn(user_id: int, domain: str, role: str, content: str) -> None:
    key = (user_id, domain)
    if key not in _store:
        if _persist_enabled():
            _store[key] = deque(_load_sqlite(user_id, domain), maxlen=_max_messages())
        else:
            _store[key] = deque(maxlen=_max_messages())
    _store[key].append(AgentMessage(role=role, content=content))
    if _persist_enabled():
        _append_sqlite(user_id, domain, role, content)


def clear_history(user_id: int, domain: str) -> None:
    _store.pop((user_id, domain), None)
    _clear_sqlite(user_id, domain)


def clear_all_history(user_id: int, domains: list[str] | None = None) -> None:
    """Reset session layer for all (or specified) domains."""
    from shared.memory.constants import AGENT_DOMAINS

    for dom in domains or list(AGENT_DOMAINS):
        clear_history(user_id, dom)


def history_as_api(user_id: int, domain: str) -> list[AgentMessage]:
    return get_history(user_id, domain)


class SessionMemory:
    """MemoryLayer: does not add block to system prompt (history goes in messages)."""

    def __init__(self, domain: str) -> None:
        self._domain = domain

    async def read(self, ctx: AgentContext) -> str:
        return ""

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        if turn.content:
            append_turn(ctx.user_id, self._domain, turn.role, turn.content)
