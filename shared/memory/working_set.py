"""Short-lived working set: entities inferred from recent turns for follow-ups.

Locale category tokens and extraction patterns belong in ``routing.yaml``
(``host.working_set.*``). Optional SQLite persistence mirrors session memory.
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
_lock = threading.Lock()
_store: dict[tuple[int, str], "WorkingSet"] = {}
_sqlite_ready = False

_KINDS = frozenset({"categories", "dates", "notes", "entities"})


def _max_items() -> int:
    from shared.memory.config import load_memory_config

    raw = (load_memory_config().get("working_set") or {}).get("max_items", 12)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 12


def _format_notes_n() -> int:
    from shared.memory.config import load_memory_config

    raw = (load_memory_config().get("working_set") or {}).get("format_notes", 4)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 4


def _format_entities_n() -> int:
    from shared.memory.config import load_memory_config

    raw = (load_memory_config().get("working_set") or {}).get("format_entities", 6)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 6

_DEFAULT_CATEGORY_PATTERNS = (
    r"\bfood\b",
    r"\btransport\b",
    r"\bsubscription\w*\b",
    r"\bhealth\b",
)
_DEFAULT_CHART_KEY_PATTERN = r"\b(?:chart_[a-z0-9_]+|fs:[a-z0-9_]+)\b"
_DEFAULT_NOTE_PATH_PATTERN = r"([\w./\-]+\.md)\b"

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
    return (os.environ.get("MEMORY_SESSION_PERSIST") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _db_path() -> Path:
    raw = os.environ.get("AGENT_MEMORY_DB", "").strip()
    return Path(raw) if raw else Path("memory.db")


def _working_set_block() -> dict:
    from shared.agent.config import load_routing_config

    host = load_routing_config().get("host") or {}
    block = host.get("working_set") or {}
    return block if isinstance(block, dict) else {}


@lru_cache(maxsize=1)
def _category_hint_re() -> re.Pattern[str]:
    block = _working_set_block()
    raw = block.get("category_patterns") or list(_DEFAULT_CATEGORY_PATTERNS)
    if isinstance(raw, str):
        parts = [raw]
    else:
        parts = [str(p) for p in raw if str(p).strip()]
    if not parts:
        parts = list(_DEFAULT_CATEGORY_PATTERNS)
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


@lru_cache(maxsize=1)
def _chart_key_re() -> re.Pattern[str]:
    block = _working_set_block()
    pat = str(block.get("chart_key_pattern") or _DEFAULT_CHART_KEY_PATTERN).strip()
    return re.compile(pat or _DEFAULT_CHART_KEY_PATTERN, re.IGNORECASE)


@lru_cache(maxsize=1)
def _note_path_re() -> re.Pattern[str]:
    block = _working_set_block()
    pat = str(block.get("note_path_pattern") or _DEFAULT_NOTE_PATH_PATTERN).strip()
    return re.compile(pat or _DEFAULT_NOTE_PATH_PATTERN)


def clear_working_set_pattern_cache() -> None:
    _category_hint_re.cache_clear()
    _chart_key_re.cache_clear()
    _note_path_re.cache_clear()


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
    entities: OrderedDict[str, None] = field(default_factory=OrderedDict)

    def _bucket(self, kind: str) -> OrderedDict[str, None]:
        if kind == "categories":
            return self.categories
        if kind == "dates":
            return self.dates
        if kind == "notes":
            return self.notes
        if kind == "entities":
            return self.entities
        raise KeyError(kind)

    def _touch(self, bucket: OrderedDict[str, None], name: str) -> None:
        key = name.strip()
        if not key:
            return
        bucket.pop(key, None)
        bucket[key] = None
        while len(bucket) > _max_items():
            bucket.popitem(last=False)

    def touch_category(self, name: str) -> None:
        self._touch(self.categories, name)

    def touch_date(self, value: str) -> None:
        self._touch(self.dates, value)

    def touch_note(self, value: str) -> None:
        self._touch(self.notes, value)

    def touch_entity(self, value: str) -> None:
        self._touch(self.entities, value)

    def touch_kind(self, kind: str, value: str) -> None:
        kind = (kind or "").strip().lower()
        if kind not in _KINDS:
            raise KeyError(kind)
        self._touch(self._bucket(kind), value)

    def format(self) -> str:
        parts: list[str] = []
        if self.categories:
            parts.append("categories: " + ", ".join(self.categories.keys()))
        if self.dates:
            parts.append("dates: " + ", ".join(self.dates.keys()))
        if self.notes:
            parts.append(
                "notes: " + ", ".join(list(self.notes.keys())[-_format_notes_n():])
            )
        if self.entities:
            parts.append(
                "entities: "
                + ", ".join(list(self.entities.keys())[-_format_entities_n():])
            )
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
            if kind in _KINDS:
                ws.touch_kind(kind, value)
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
            conn.execute(
                """
                DELETE FROM working_set WHERE rowid IN (
                  SELECT rowid FROM working_set
                  WHERE user_id=? AND domain=? AND kind=?
                  ORDER BY touched_at DESC
                  LIMIT -1 OFFSET ?
                )
                """,
                (user_id, domain, kind, _max_items()),
            )
            conn.commit()
    except sqlite3.Error as e:
        log.warning("working_set sqlite upsert failed: %s", e)


def _delete_sqlite(
    user_id: int,
    domain: str,
    *,
    kind: str | None = None,
    value: str | None = None,
) -> None:
    if not _persist_enabled():
        return
    _ensure_sqlite()
    try:
        with sqlite3.connect(str(_db_path())) as conn:
            if kind and value:
                conn.execute(
                    "DELETE FROM working_set WHERE user_id=? AND domain=? AND kind=? AND value=?",
                    (user_id, domain, kind, value),
                )
            elif kind:
                conn.execute(
                    "DELETE FROM working_set WHERE user_id=? AND domain=? AND kind=?",
                    (user_id, domain, kind),
                )
            else:
                conn.execute(
                    "DELETE FROM working_set WHERE user_id=? AND domain=?",
                    (user_id, domain),
                )
            conn.commit()
    except sqlite3.Error as e:
        log.warning("working_set sqlite delete failed: %s", e)


def get_working_set(user_id: int, domain: str) -> WorkingSet:
    with _lock:
        k = _key(user_id, domain)
        if k not in _store:
            _store[k] = _load_sqlite(user_id, domain) if _persist_enabled() else WorkingSet()
        return _store[k]


def pin_entity(user_id: int, domain: str, kind: str, value: str) -> WorkingSet:
    """Pin an explicit entity into the working set (agent tool / observe).

    ``kind`` is one of categories|dates|notes|entities, or a free prefix
    (e.g. chart / task) stored as ``entities`` value ``prefix:value``.
    """
    raw_kind = (kind or "entities").strip().lower() or "entities"
    val = (value or "").strip()
    if not val:
        return get_working_set(user_id, domain)
    if raw_kind in _KINDS:
        kind_n, stored = raw_kind, val
    else:
        kind_n, stored = "entities", f"{raw_kind}:{val}"
    ws = get_working_set(user_id, domain)
    ws.touch_kind(kind_n, stored)
    _upsert_sqlite(user_id, domain, kind_n, stored)
    return ws


def clear_entities(
    user_id: int,
    domain: str,
    *,
    kind: str = "",
    value: str = "",
) -> WorkingSet:
    kind_n = (kind or "").strip().lower()
    val = (value or "").strip()
    ws = get_working_set(user_id, domain)
    if kind_n and kind_n not in _KINDS:
        return ws
    with _lock:
        if not kind_n:
            ws.categories.clear()
            ws.dates.clear()
            ws.notes.clear()
            ws.entities.clear()
            _delete_sqlite(user_id, domain)
        elif val:
            ws._bucket(kind_n).pop(val, None)
            _delete_sqlite(user_id, domain, kind=kind_n, value=val)
        else:
            ws._bucket(kind_n).clear()
            _delete_sqlite(user_id, domain, kind=kind_n)
    return ws


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


def observe_tool_output(user_id: int, domain: str, tool_name: str, content: str) -> WorkingSet:
    """Extract durable follow-up keys from successful tool output (no PII bodies logged)."""
    ws = observe_text(user_id, domain, content or "")
    text = content or ""
    for m in _chart_key_re().finditer(text):
        key = m.group(0)
        ent = f"chart:{key}"
        ws.touch_entity(ent)
        _upsert_sqlite(user_id, domain, "entities", ent)
    for m in _note_path_re().finditer(text):
        path = (m.group(1) if m.lastindex else m.group(0)).strip()
        if not path or path.startswith("http"):
            continue
        ws.touch_note(path)
        _upsert_sqlite(user_id, domain, "notes", path)
    # Lightweight tool breadcrumb (name only — not arguments/bodies).
    name = (tool_name or "").strip()
    if name:
        ent = f"tool:{name}"
        ws.touch_entity(ent)
        _upsert_sqlite(user_id, domain, "entities", ent)
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
