"""Short-lived working set: entities inferred from recent turns for follow-ups.

Locale category tokens belong in ``routing.yaml`` (``host.working_set.category_patterns``).
Optional SQLite persistence mirrors session memory (survives process restarts).
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from shared.agent.types import AgentContext, AgentMessage

log = logging.getLogger("shared.memory.working_set")

_ISO = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_MAX_ITEMS = 12
_lock = threading.Lock()
_store: dict[tuple[int, str], "WorkingSet"] = {}
_sqlite_ready = False

_DEFAULT_CATEGORY_PATTERNS = (
    r"\bfood\b",
    r"\btransport\b",
    r"\bsubscription\w*\b",
    r"\bhealth\b",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS working_set (
  user_id INTEGER NOT NULL,
  domain TEXT NOT NULL,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  touched_at TEXT NOT NULL,
  PRIMARY KEY (user_id, domain, kind, value)
);
CREATE INDEX IF NOT EXISTS idx_working_set_user_domain
  ON working_set(user_id, domain, touched_at);
"""


def _persist_enabled() -> bool:
    raw = (os.environ.get("MEMORY_WORKING_SET_PERSIST") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    # Default: follow session persist when unset.
    return (os.environ.get("MEMORY_SESSION_PERSIST") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _db_path() -> Path:
    raw = os.environ.get("AGENT_MEMORY_DB", "").strip()
    return Path(raw) if raw else Path("memory.db")


@lru_cache(maxsize=1)
def _category_hint_re() -> re.Pattern[str]:
    from shared.agent.config import load_routing_config

    host = load_routing_config().get("host") or {}
    block = host.get("working_set") or {}
    raw = block.get("category_patterns") or list(_DEFAULT_CATEGORY_PATTERNS)
    if isinstance(raw, str):
        parts = [raw]
    else:
        parts = [str(p) for p in raw if str(p).strip()]
    if not parts:
        parts = list(_DEFAULT_CATEGORY_PATTERNS)
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


def clear_working_set_pattern_cache() -> None:
    _category_hint_re.cache_clear()


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class WorkingSet:
    categories: OrderedDict[str, None] = field(default_factory=OrderedDict)
    dates: OrderedDict[str, None] = field(default_factory=OrderedDict)
    notes: OrderedDict[str, None] = field(default_factory=OrderedDict)

    def _touch(self, bucket: OrderedDict[str, None], name: str) -> None:
        key = name.strip()
        if not key:
            return
        bucket.pop(key, None)
        bucket[key] = None
        while len(bucket) > _MAX_ITEMS:
            bucket.popitem(last=False)

    def touch_category(self, name: str) -> None:
        self._touch(self.categories, name)

    def touch_date(self, value: str) -> None:
        self._touch(self.dates, value)

    def touch_note(self, value: str) -> None:
        self._touch(self.notes, value)

    def format(self) -> str:
        parts: list[str] = []
        if self.categories:
            parts.append("categories: " + ", ".join(self.categories.keys()))
        if self.dates:
            parts.append("dates: " + ", ".join(self.dates.keys()))
        if self.notes:
            parts.append("notes: " + ", ".join(list(self.notes.keys())[-4:]))
        if not parts:
            return ""
        return "Working set (recent context):\n" + "\n".join(f"- {p}" for p in parts)


def _key(user_id: int, domain: str) -> tuple[int, str]:
    return (int(user_id), str(domain or "general"))


def _load_sqlite(user_id: int, domain: str) -> WorkingSet:
    ws = WorkingSet()
    if not _persist_enabled():
        return ws
    _ensure_sqlite()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            rows = conn.execute(
                "SELECT kind, value FROM working_set WHERE user_id=? AND domain=? "
                "ORDER BY touched_at ASC",
                (user_id, domain),
            ).fetchall()
        for kind, value in rows:
            if kind == "categories":
                ws.touch_category(value)
            elif kind == "dates":
                ws.touch_date(value)
            elif kind == "notes":
                ws.touch_note(value)
    except sqlite3.Error as e:
        log.warning("working_set sqlite load failed: %s", e)
    return ws


def _upsert_sqlite(user_id: int, domain: str, kind: str, value: str) -> None:
    if not _persist_enabled():
        return
    _ensure_sqlite()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            conn.execute(
                "INSERT INTO working_set(user_id, domain, kind, value, touched_at) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(user_id, domain, kind, value) DO UPDATE SET touched_at=excluded.touched_at",
                (user_id, domain, kind, value, _now()),
            )
            # prune oldest beyond max for this kind
            conn.execute(
                """
                DELETE FROM working_set WHERE rowid IN (
                  SELECT rowid FROM working_set
                  WHERE user_id=? AND domain=? AND kind=?
                  ORDER BY touched_at DESC
                  LIMIT -1 OFFSET ?
                )
                """,
                (user_id, domain, kind, _MAX_ITEMS),
            )
            conn.commit()
    except sqlite3.Error as e:
        log.warning("working_set sqlite upsert failed: %s", e)


def get_working_set(user_id: int, domain: str) -> WorkingSet:
    with _lock:
        k = _key(user_id, domain)
        if k not in _store:
            _store[k] = _load_sqlite(user_id, domain) if _persist_enabled() else WorkingSet()
        return _store[k]


def observe_text(user_id: int, domain: str, text: str) -> WorkingSet:
    ws = get_working_set(user_id, domain)
    t = text or ""
    for m in _ISO.finditer(t):
        ws.touch_date(m.group(1))
        _upsert_sqlite(user_id, domain, "dates", m.group(1))
    for m in _category_hint_re().finditer(t):
        token = m.group(0)
        ws.touch_category(token)
        _upsert_sqlite(user_id, domain, "categories", token)
    return ws


def clear_working_set(user_id: int | None = None) -> None:
    with _lock:
        if user_id is None:
            _store.clear()
        else:
            dead = [k for k in _store if k[0] == int(user_id)]
            for k in dead:
                _store.pop(k, None)
    if not _persist_enabled():
        return
    _ensure_sqlite()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            if user_id is None:
                conn.execute("DELETE FROM working_set")
            else:
                conn.execute("DELETE FROM working_set WHERE user_id=?", (int(user_id),))
            conn.commit()
    except sqlite3.Error as e:
        log.warning("working_set sqlite clear failed: %s", e)


class WorkingSetMemory:
    """Memory layer that injects the recent working set into the system prompt."""

    async def read(self, ctx: AgentContext) -> str:
        ws = get_working_set(ctx.user_id, ctx.domain)
        observe_text(ctx.user_id, ctx.domain, ctx.question or "")
        return ws.format()

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        observe_text(ctx.user_id, ctx.domain, turn.content or "")


def working_set_layer() -> WorkingSetMemory:
    return WorkingSetMemory()
