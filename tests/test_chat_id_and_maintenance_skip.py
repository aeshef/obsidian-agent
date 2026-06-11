"""chat_id for schedulers + maintenance exit code 3 (LLM offline skip)."""
from __future__ import annotations

from pathlib import Path

from knowledge_bot.services.vault_maintenance.runner import _step_failed
from planning_bot.app.chatid_store import load_chat_id, maybe_persist_chat_id


def test_load_chat_id_falls_back_to_telegram_user_id(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_USER_ID", "553480079")
    assert load_chat_id(tmp_path / "missing.txt") == 553480079


def test_load_chat_id_prefers_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_USER_ID", "111")
    f = tmp_path / "CHAT_ID.txt"
    f.write_text("999\n", encoding="utf-8")
    assert load_chat_id(f) == 999


def test_maybe_persist_chat_id_writes_file(tmp_path: Path):
    f = tmp_path / "CHAT_ID.txt"
    cid = maybe_persist_chat_id(f, 42, current=None)
    assert cid == 42
    assert f.read_text(encoding="utf-8").strip() == "42"


def test_maintenance_step_failed_treats_llm_skip_as_ok():
    assert not _step_failed(0)
    assert not _step_failed(3)
    assert _step_failed(1)
