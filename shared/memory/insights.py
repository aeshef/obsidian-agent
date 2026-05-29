"""Layer 5: confirmed insights + candidate accumulation (SQLite, stdlib).

Works on Python 3.9 without external infra. Synth engine (synth.py) writes candidates;
user confirms via /memory; confirmed ones read into system prompt.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from shared.agent.types import AgentContext, AgentMessage
from shared.domain_messages import dmsg
from shared.memory.constants import GLOBAL_DOMAIN

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
            self._ensured = True
        return conn

    def read_confirmed(self, user_id: int, domain: str, *, limit: int = 12) -> list[str]:
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT pattern_text FROM insights WHERE user_id=? AND domain=? "
                    "ORDER BY confirmed_at DESC LIMIT ?",
                    (user_id, domain, limit),
                ).fetchall()
            return [r["pattern_text"] for r in rows]
        except sqlite3.Error as e:
            log.warning("read_confirmed failed: %s", e)
            return []

    def record_candidates(
        self, user_id: int, domain: str, patterns: list[str], *, evidence: str = ""
    ) -> list[tuple[int, str]]:
        """Upsert candidates with confirmation accumulation. Returns those reaching threshold."""
        now = _now_iso()
        threshold = confirmations_threshold()
        pushable: list[tuple[int, str]] = []
        try:
            with self._conn() as conn:
                for raw in patterns:
                    text = (raw or "").strip()
                    if not text:
                        continue
                    existing = conn.execute(
                        "SELECT id, confirmations FROM pending_insights "
                        "WHERE user_id=? AND domain=? AND pattern_text=? AND status='pending'",
                        (user_id, domain, text),
                    ).fetchone()
                    if existing:
                        new_count = existing["confirmations"] + 1
                        conn.execute(
                            "UPDATE pending_insights SET confirmations=?, last_seen=? WHERE id=?",
                            (new_count, now, existing["id"]),
                        )
                        if new_count >= threshold:
                            pushable.append((existing["id"], text))
                    else:
                        conn.execute(
                            "INSERT INTO pending_insights (user_id, domain, pattern_text, evidence, "
                            "confirmations, status, created_at, last_seen) "
                            "VALUES (?, ?, ?, ?, 1, 'pending', ?, ?)",
                            (user_id, domain, text, evidence, now, now),
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
                    "SELECT user_id, domain, pattern_text FROM pending_insights WHERE id=?",
                    (pending_id,),
                ).fetchone()
                if not row:
                    return False
                conn.execute(
                    "INSERT INTO insights (user_id, domain, pattern_text, confirmed_at) VALUES (?, ?, ?, ?)",
                    (row["user_id"], row["domain"], row["pattern_text"], now),
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

    def prune_expired(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=pending_ttl_days())).isoformat(timespec="seconds")
        try:
            with self._conn() as conn:
                cur = conn.execute(
                    "DELETE FROM pending_insights WHERE status='pending' AND last_seen < ?",
                    (cutoff,),
                )
                conn.commit()
                return cur.rowcount
        except sqlite3.Error as e:
            log.warning("prune_expired failed: %s", e)
            return 0


@lru_cache(maxsize=1)
def get_store() -> InsightsStore:
    return InsightsStore()


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
        patterns = get_store().read_confirmed(ctx.user_id, GLOBAL_DOMAIN, limit=lim)
        if not patterns:
            return ""
        body = "\n".join(f"- {p}" for p in patterns)
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
        patterns = get_store().read_confirmed(ctx.user_id, self._domain, limit=lim)
        if not patterns:
            return ""
        body = "\n".join(f"- {p}" for p in patterns)
        return f"{self._header}\n{body}"

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        pass
