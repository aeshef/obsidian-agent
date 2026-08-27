"""Layer 5: confirmed insights + candidate accumulation (SQLite, stdlib).

Works on Python 3.9 without external infra. Synth engine (synth.py) writes candidates;
user confirms via Memory menu; confirmed ones read into system prompt.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from shared.agent.types import AgentContext, AgentMessage
from shared.domain_messages import dmsg
from shared.memory.constants import GLOBAL_DOMAIN
from shared.memory.insight_format import (
    KIND_DURABLE,
    format_confirmed_prompt_line,
    format_date_short,
    normalize_kind,
)

log = logging.getLogger("shared.memory.insights")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def memory_db_path() -> Path:
    raw = os.environ.get("AGENT_MEMORY_DB", "").strip()
    return Path(raw) if raw else Path("memory.db")


def confirmations_threshold() -> int:
    try:
        return max(1, int(os.environ.get("INSIGHTS_CONFIRMATIONS_THRESHOLD", "3")))
    except ValueError:
        return 3


def pending_ttl_days() -> int:
    try:
        return max(1, int(os.environ.get("INSIGHTS_PENDING_TTL_DAYS", "30")))
    except ValueError:
        return 30


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    pattern_text TEXT NOT NULL,
    evidence TEXT,
    confirmations INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    pattern_text TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insights_user_domain ON insights(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_pending_user_domain ON pending_insights(user_id, domain);
"""


def _normalize_candidate_items(
    patterns: Iterable[str | tuple[str, str] | dict[str, str]],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in patterns:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("pattern") or "").strip()
            kind = normalize_kind(item.get("kind"))
        elif isinstance(item, tuple):
            text = str(item[0] or "").strip()
            kind = normalize_kind(item[1] if len(item) > 1 else KIND_DURABLE)
        else:
            text = str(item or "").strip()
            kind = KIND_DURABLE
        if text:
            out.append((text, kind))
    return out


class InsightsStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or memory_db_path()
        self._ensured = False

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        if not self._ensured:
            conn.executescript(_SCHEMA)
            conn.commit()
            self._migrate_schema(conn)
            self._ensured = True
        return conn

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        for table in ("pending_insights", "insights"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "kind" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN kind TEXT NOT NULL DEFAULT '{KIND_DURABLE}'"
                )
        conn.commit()

    def _periodic_cutoff(self) -> str:
        from shared.memory.config import periodic_ttl_days

        return (
            datetime.now(timezone.utc) - timedelta(days=periodic_ttl_days())
        ).isoformat(timespec="seconds")

    def read_confirmed_records(
        self, user_id: int, domain: str, *, limit: int = 12
    ) -> list[dict]:
        cutoff = self._periodic_cutoff()
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT pattern_text, confirmed_at, kind FROM insights "
                    "WHERE user_id=? AND domain=? "
                    "AND (kind != 'periodic' OR confirmed_at >= ?) "
                    "ORDER BY confirmed_at DESC LIMIT ?",
                    (user_id, domain, cutoff, limit),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            log.warning("read_confirmed_records failed: %s", e)
            return []

    def read_confirmed(self, user_id: int, domain: str, *, limit: int = 12) -> list[str]:
        return [r["pattern_text"] for r in self.read_confirmed_records(user_id, domain, limit=limit)]

    def format_confirmed_for_prompt(
        self, user_id: int, domain: str, *, limit: int = 12
    ) -> list[str]:
        lines: list[str] = []
        for row in self.read_confirmed_records(user_id, domain, limit=limit):
            lines.append(
                format_confirmed_prompt_line(
                    date=format_date_short(row.get("confirmed_at")),
                    text=row.get("pattern_text") or "",
                )
            )
        return lines

    def record_candidates(
        self,
        user_id: int,
        domain: str,
        patterns: Iterable[str | tuple[str, str] | dict[str, str]],
        *,
        evidence: str = "",
    ) -> list[tuple[int, str]]:
        """Upsert candidates with confirmation accumulation. Returns those reaching threshold."""
        items = _normalize_candidate_items(patterns)
        if not items:
            return []

        now = _now_iso()
        threshold = confirmations_threshold()
        pushable: list[tuple[int, str]] = []
        try:
            with self._conn() as conn:
                for text, kind in items:
                    existing = conn.execute(
                        "SELECT id, confirmations FROM pending_insights "
                        "WHERE user_id=? AND domain=? AND pattern_text=? AND status='pending'",
                        (user_id, domain, text),
                    ).fetchone()
                    if existing:
                        new_count = existing["confirmations"] + 1
                        conn.execute(
                            "UPDATE pending_insights SET confirmations=?, last_seen=?, kind=? WHERE id=?",
                            (new_count, now, kind, existing["id"]),
                        )
                        if new_count >= threshold:
                            pushable.append((existing["id"], text))
                    else:
                        conn.execute(
                            "INSERT INTO pending_insights (user_id, domain, pattern_text, evidence, "
                            "confirmations, status, created_at, last_seen, kind) "
                            "VALUES (?, ?, ?, ?, 1, 'pending', ?, ?, ?)",
                            (user_id, domain, text, evidence, now, now, kind),
                        )
                        if threshold <= 1:
                            row = conn.execute(
                                "SELECT id FROM pending_insights WHERE user_id=? AND domain=? "
                                "AND pattern_text=? AND status='pending'",
                                (user_id, domain, text),
                            ).fetchone()
                            if row:
                                pushable.append((row["id"], text))
                conn.commit()
        except sqlite3.Error as e:
            log.warning("record_candidates failed: %s", e)
        return pushable

    def list_pending(self, user_id: int, domain: str | None = None) -> list[dict]:
        try:
            with self._conn() as conn:
                if domain:
                    rows = conn.execute(
                        "SELECT * FROM pending_insights WHERE user_id=? AND domain=? AND status='pending' "
                        "ORDER BY confirmations DESC, last_seen DESC",
                        (user_id, domain),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM pending_insights WHERE user_id=? AND status='pending' "
                        "ORDER BY confirmations DESC, last_seen DESC",
                        (user_id,),
                    ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            log.warning("list_pending failed: %s", e)
            return []

    def confirm(self, pending_id: int) -> bool:
        now = _now_iso()
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT user_id, domain, pattern_text, kind FROM pending_insights WHERE id=?",
                    (pending_id,),
                ).fetchone()
                if not row:
                    return False
                kind = normalize_kind(row["kind"] if "kind" in row.keys() else KIND_DURABLE)
                conn.execute(
                    "INSERT INTO insights (user_id, domain, pattern_text, confirmed_at, kind) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (row["user_id"], row["domain"], row["pattern_text"], now, kind),
                )
                conn.execute(
                    "UPDATE pending_insights SET status='confirmed' WHERE id=?", (pending_id,)
                )
                conn.commit()
            return True
        except sqlite3.Error as e:
            log.warning("confirm failed: %s", e)
            return False

    def reject(self, pending_id: int) -> bool:
        try:
            with self._conn() as conn:
                conn.execute(
                    "UPDATE pending_insights SET status='rejected' WHERE id=?", (pending_id,)
                )
                conn.commit()
            return True
        except sqlite3.Error as e:
            log.warning("reject failed: %s", e)
            return False

    def clear_pending(self, user_id: int, domain: str | None = None) -> int:
        try:
            with self._conn() as conn:
                if domain:
                    cur = conn.execute(
                        "UPDATE pending_insights SET status='rejected' "
                        "WHERE user_id=? AND domain=? AND status='pending'",
                        (user_id, domain),
                    )
                else:
                    cur = conn.execute(
                        "UPDATE pending_insights SET status='rejected' "
                        "WHERE user_id=? AND status='pending'",
                        (user_id,),
                    )
                conn.commit()
                return cur.rowcount
        except sqlite3.Error as e:
            log.warning("clear_pending failed: %s", e)
            return 0

    def clear_confirmed(self, user_id: int, domain: str | None = None) -> int:
        try:
            with self._conn() as conn:
                if domain:
                    cur = conn.execute(
                        "DELETE FROM insights WHERE user_id=? AND domain=?",
                        (user_id, domain),
                    )
                else:
                    cur = conn.execute("DELETE FROM insights WHERE user_id=?", (user_id,))
                conn.commit()
                return cur.rowcount
        except sqlite3.Error as e:
            log.warning("clear_confirmed failed: %s", e)
            return 0

    def prune_expired(self) -> int:
        pending_cutoff = (
            datetime.now(timezone.utc) - timedelta(days=pending_ttl_days())
        ).isoformat(timespec="seconds")
        periodic_cutoff = self._periodic_cutoff()
        removed = 0
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    "DELETE FROM pending_insights WHERE status='pending' AND last_seen < ?",
                    (pending_cutoff,),
                )
                removed += cur.rowcount
                cur = conn.execute(
                    "DELETE FROM insights WHERE kind='periodic' AND confirmed_at < ?",
                    (periodic_cutoff,),
                )
                removed += cur.rowcount
                conn.commit()
        except sqlite3.Error as e:
            log.warning("prune_expired failed: %s", e)
        return removed


@lru_cache(maxsize=8)
def _store_for(path: str) -> InsightsStore:
    return InsightsStore(Path(path))


def get_store() -> InsightsStore:
    """Return the process InsightsStore for the current AGENT_MEMORY_DB path."""
    return _store_for(str(memory_db_path().resolve()))


get_store.cache_clear = _store_for.cache_clear  # type: ignore[attr-defined]


class GlobalInsightsMemory:
    """MemoryLayer: cross-domain confirmed observations (domain=global)."""

    def __init__(
        self,
        *,
        header: str | None = None,
        limit: int | None = None,
    ) -> None:
        self._header = header or dmsg("memory_insights", "global_header")
        self._limit = limit

    async def read(self, ctx: AgentContext) -> str:
        from shared.memory.config import insight_limits

        lim = self._limit if self._limit is not None else insight_limits()[0]
        if lim <= 0:
            return ""
        lines = get_store().format_confirmed_for_prompt(ctx.user_id, GLOBAL_DOMAIN, limit=lim)
        if not lines:
            return ""
        body = "\n".join(lines)
        return f"{self._header}\n{body}"

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        pass


class InsightsMemory:
    """MemoryLayer: domain confirmed observations in system prompt."""

    def __init__(
        self,
        domain: str,
        *,
        header: str | None = None,
        limit: int | None = None,
    ) -> None:
        self._domain = domain
        self._header = header or dmsg("memory_insights", "domain_header", domain=domain)
        self._limit = limit

    async def read(self, ctx: AgentContext) -> str:
        from shared.memory.config import insight_limits

        lim = self._limit if self._limit is not None else insight_limits()[1]
        if lim <= 0:
            return ""
        lines = get_store().format_confirmed_for_prompt(ctx.user_id, self._domain, limit=lim)
        if not lines:
            return ""
        body = "\n".join(lines)
        return f"{self._header}\n{body}"

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        pass
