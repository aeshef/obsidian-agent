"""Action log write format and legacy parse."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from planning_bot.core.config import ACTION_LOG_PREFIX
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.action_log_format import content_for_parse, format_log_entry, needs_repair
from planning_bot.services.action_log_parser import parse_log_content
from planning_bot.services.action_logger import ActionLogger

_LOG_MONTH = "2026-06"
_FIXED_NOW = datetime(2026, 6, 15, 12, 0, 0)


@pytest.fixture
def action_log_now(monkeypatch):
    """log_action names files by datetime.now() — pin month so tests are calendar-stable."""
    fake_dt = MagicMock(wraps=datetime)
    fake_dt.now.return_value = _FIXED_NOW
    monkeypatch.setattr("planning_bot.services.action_log.write.datetime", fake_dt)


def _type_label() -> str:
    return pdmsg("log_entry_type_label", default="**Type:**")


def _data_label() -> str:
    return pdmsg("log_entry_data_label", default="**Data:**")


def test_log_action_writes_canonical_format(action_log_now):
    with tempfile.TemporaryDirectory() as tmp:
        logger = ActionLogger(Path(tmp))
        logger.log_action("task_completed", {"title": "T", "task_id": "abc12345"})
        log_file = Path(tmp) / f"{ACTION_LOG_PREFIX}{_LOG_MONTH}.md"
        text = log_file.read_text(encoding="utf-8")
        t = _type_label()
        d = _data_label()
        assert f"{t} task_completed" in text
        assert "{'task_" not in text
        assert f"\n\n{d}" in text
        assert f"{d}\n```json\n" in text
        assert text.index(t) < text.index(d)
        entries = logger._load_task_events([_LOG_MONTH])
        assert len(entries) == 1
        assert entries[0]["type"] == "task_completed"


def test_load_legacy_corrupt_entries():
    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / f"{ACTION_LOG_PREFIX}{_LOG_MONTH}.md"
        t = _type_label()
        d = _data_label()
        log_file.write_text(
            "---\n\n## 2026-06-03 17:20:02\n\n"
            f"{t} {{'task_completed'}}{d}\n```json\n"
            '{"title": "X", "task_id": "deadbeef"}\n```\n',
            encoding="utf-8",
        )
        logger = ActionLogger(Path(tmp))
        entries = logger._load_task_events([_LOG_MONTH])
        assert len(entries) == 1
        assert entries[0]["type"] == "task_completed"
        assert entries[0]["data"]["task_id"] == "deadbeef"


def test_parse_glued_separator_in_memory():
    t = _type_label()
    d = _data_label()
    raw = (
        f"---## 2026-06-04 12:26:02\n\n{t} task_moved\n\n"
        f'{d}\n```json\n{{"title": "T", "task_id": "abcd1234"}}\n```\n'
    )
    events = parse_log_content(content_for_parse(raw))
    assert len(events) == 1
    assert events[0]["type"] == "task_moved"


def test_canonical_entry_does_not_need_repair():
    entry = format_log_entry("2026-06-05 12:00:00", "task_moved", {"title": "T", "from": "A", "to": "B"})
    assert not needs_repair(entry)


def test_double_append_no_glued_separator(action_log_now):
    with tempfile.TemporaryDirectory() as tmp:
        logger = ActionLogger(Path(tmp))
        logger.log_action("task_moved", {"title": "A", "task_id": "a1b2c3d4", "from": "X", "to": "Y"})
        logger.log_action("task_completed", {"title": "A", "task_id": "a1b2c3d4"})
        text = (Path(tmp) / f"{ACTION_LOG_PREFIX}{_LOG_MONTH}.md").read_text(encoding="utf-8")
        assert "---##" not in text
        assert text.count("## ") >= 2
        entries = logger._load_task_events([_LOG_MONTH])
        assert len(entries) == 2
