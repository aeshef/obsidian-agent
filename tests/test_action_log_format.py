"""Action log write format and legacy parse."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from planning_bot.core.config import ACTION_LOG_PREFIX
from planning_bot.services.action_logger import ActionLogger


def test_log_action_writes_canonical_format():
    with tempfile.TemporaryDirectory() as tmp:
        logger = ActionLogger(Path(tmp))
        logger.log_action("task_completed", {"title": "T", "task_id": "abc12345"})
        log_file = Path(tmp) / f"{ACTION_LOG_PREFIX}2026-06.md"
        text = log_file.read_text(encoding="utf-8")
        assert "**Тип:** task_completed" in text
        assert "{'task_" not in text
        assert "\n\n**Данные:**" in text
        assert "**Данные:**\n```json\n" in text
        assert text.index("**Тип:**") < text.index("**Данные:**")
        entries = logger._load_task_events(["2026-06"])
        assert len(entries) == 1
        assert entries[0]["type"] == "task_completed"


def test_load_legacy_corrupt_entries():
    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / f"{ACTION_LOG_PREFIX}2026-06.md"
        log_file.write_text(
            "---\n\n## 2026-06-03 17:20:02\n\n"
            "**Тип:** {'task_completed'}**Данные:**\n```json\n"
            '{"title": "X", "task_id": "deadbeef"}\n```\n',
            encoding="utf-8",
        )
        logger = ActionLogger(Path(tmp))
        entries = logger._load_task_events(["2026-06"])
        assert len(entries) == 1
        assert entries[0]["type"] == "task_completed"
        assert entries[0]["data"]["task_id"] == "deadbeef"
