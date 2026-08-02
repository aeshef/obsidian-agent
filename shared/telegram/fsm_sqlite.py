"""SQLite-backed aiogram FSM storage (survives process restarts)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import aiosqlite
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

log = logging.getLogger("shared.telegram.fsm_sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fsm (
  key TEXT PRIMARY KEY,
  state TEXT,
  data TEXT NOT NULL DEFAULT '{}'
);
"""


def _key_str(key: StorageKey) -> str:
    return "|".join(
        [
            str(key.bot_id),
            str(key.chat_id),
            str(key.user_id),
            str(key.thread_id if key.thread_id is not None else ""),
            str(key.business_connection_id or ""),
            str(key.destiny or "default"),
        ]
    )


def default_fsm_db_path() -> Path:
    env = (os.environ.get("FSM_DB_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    root = (os.environ.get("AGENT_ROOT") or "").strip()
    base = Path(root) if root else Path.cwd()
    return base / "data" / "fsm.sqlite"


class SQLiteStorage(BaseStorage):
    """Persist FSM state/data in a local SQLite file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else default_fsm_db_path()
        self._db: aiosqlite.Connection | None = None

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(self._path))
            await self._db.execute("PRAGMA journal_mode=WAL;")
            await self._db.execute(_SCHEMA)
            await self._db.commit()
            log.info("FSM SQLite storage at %s", self._path)
        return self._db

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        db = await self._conn()
        await db.execute(
            """
            INSERT INTO fsm(key, state, data) VALUES(?, ?, '{}')
            ON CONFLICT(key) DO UPDATE SET state=excluded.state
            """,
            (_key_str(key), value),
        )
        await db.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        db = await self._conn()
        async with db.execute(
            "SELECT state FROM fsm WHERE key=?", (_key_str(key),)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        payload = json.dumps(data or {}, ensure_ascii=False)
        db = await self._conn()
        await db.execute(
            """
            INSERT INTO fsm(key, state, data) VALUES(?, NULL, ?)
            ON CONFLICT(key) DO UPDATE SET data=excluded.data
            """,
            (_key_str(key), payload),
        )
        await db.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        db = await self._conn()
        async with db.execute(
            "SELECT data FROM fsm WHERE key=?", (_key_str(key),)
        ) as cur:
            row = await cur.fetchone()
        if not row or not row[0]:
            return {}
        try:
            raw = json.loads(row[0])
        except json.JSONDecodeError:
            return {}
        return raw if isinstance(raw, dict) else {}

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
