"""Durable working-set SQLite persistence."""
from __future__ import annotations

from pathlib import Path

from shared.memory import working_set as ws


def test_working_set_survives_reload(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEMORY_WORKING_SET_PERSIST", "1")
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "mem.db"))
    ws._sqlite_ready = False
    ws.clear_working_set()
    ws.clear_working_set_pattern_cache()

    ws.observe_text(7, "finance", "food spend on 2026-07-15")
    got = ws.get_working_set(7, "finance")
    assert any("food" in c.lower() for c in got.categories)
    assert "2026-07-15" in got.dates

    # Drop RAM cache and reload from sqlite
    ws._store.clear()
    ws._sqlite_ready = False
    again = ws.get_working_set(7, "finance")
    assert "2026-07-15" in again.dates
