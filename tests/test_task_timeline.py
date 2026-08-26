from __future__ import annotations

from planning_bot.core.config import ACTION_LOG_PREFIX
from planning_bot.services.action_log_format import format_log_entry
from planning_bot.services.action_log import ActionLogger
from planning_bot.services.kanban import KanbanBoard
from planning_bot.services.task_timeline_query import format_task_timeline
from tests.kanban_test_data import kanban_fixture


def test_get_task_history_scans_all_log_months(tmp_path):
    logs = tmp_path / "logs"
    logger = ActionLogger(logs)
    payload = {"task_id": "abc12345", "title": "Read DMBA", "category": "dev", "priority": "low"}
    (logs / f"{ACTION_LOG_PREFIX}2025-11.md").write_text(
        format_log_entry("2025-11-15 12:00:00", "task_created", payload),
        encoding="utf-8",
    )
    (logs / f"{ACTION_LOG_PREFIX}2026-06.md").write_text(
        format_log_entry(
            "2026-06-02 12:00:00",
            "task_moved",
            {"task_id": "abc12345", "title": "Read DMBA", "from": "Backlog", "to": "In progress"},
        ),
        encoding="utf-8",
    )

    history = logger.get_task_history(task_id="abc12345")
    assert len(history) == 2
    assert history[0]["type"] == "task_created"
    assert history[1]["type"] == "task_moved"


def test_format_task_timeline_includes_board_and_log(tmp_path):
    board_path = tmp_path / "board.md"
    board_path.write_text(kanban_fixture("board_parse_sections.md"), encoding="utf-8")
    logs = tmp_path / "logs"
    logger = ActionLogger(logs)
    logger.log_task_moved("Тест агента REAL", "Backlog", "In progress", task_id="c40b41a6")

    board = KanbanBoard(board_path)
    text = format_task_timeline(logger, board, task_id="c40b41a6")
    assert "c40b41a6" in text
    assert "2026-06-01" in text
    assert "task_moved" in text
    assert "n=1" in text
