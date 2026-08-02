"""SQLite FSM storage smoke tests."""
from __future__ import annotations

import pytest
from aiogram.fsm.storage.base import StorageKey

from shared.telegram.fsm_sqlite import SQLiteStorage


@pytest.mark.asyncio
async def test_sqlite_storage_roundtrip(tmp_path):
    path = tmp_path / "fsm.sqlite"
    storage = SQLiteStorage(path)
    key = StorageKey(bot_id=1, chat_id=2, user_id=3)
    await storage.set_state(key, "Form:waiting")
    await storage.set_data(key, {"bulk_ingest": True, "n": 1})
    assert await storage.get_state(key) == "Form:waiting"
    assert (await storage.get_data(key))["bulk_ingest"] is True
    await storage.update_data(key, {"n": 2})
    assert (await storage.get_data(key))["n"] == 2
    await storage.close()

    storage2 = SQLiteStorage(path)
    assert await storage2.get_state(key) == "Form:waiting"
    assert (await storage2.get_data(key))["n"] == 2
    await storage2.close()
