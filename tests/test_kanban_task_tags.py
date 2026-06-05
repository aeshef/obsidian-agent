from __future__ import annotations

from unittest.mock import patch

from planning_bot.core.config import CATEGORIES, PRIORITIES
from planning_bot.services.kanban import KanbanBoard
from planning_bot.services.kanban_format import normalize_category, task_meta_line
from planning_bot.services.kanban_parse import metadata_from_block


def test_task_meta_line_uses_schema_when_pdmsg_empty():
    with patch("planning_bot.services.kanban_format.pdmsg", return_value=""):
        line = task_meta_line("инфраструктура", "средний")
    assert "инфраструктура" in line
    assert "средний" in line
    assert "#" in line


def test_add_task_to_backlog_writes_tags(tmp_path):
    board_file = tmp_path / "board.md"
    board_file.write_text(
        "## 📋 Бэклог\n\n",
        encoding="utf-8",
    )
    board = KanbanBoard(board_file)
    with patch("planning_bot.services.kanban_format.pdmsg", return_value=""):
        tid = board.add_task_to_backlog(
            "New task", "инфраструктура", "средний", created_date="2026-06-05"
        )
    assert tid
    block = ""
    for part in board.content.split("\n\n"):
        if tid in part:
            block = part
            break
    assert block
    meta = metadata_from_block(block)
    assert meta["category"] == normalize_category("инфраструктура")
    assert meta["priority"] in PRIORITIES
    assert meta["created_date"] == "2026-06-05"


def test_normalize_category_fuzzy():
    assert normalize_category("Инфраструктура") == "инфраструктура"
    assert normalize_category(CATEGORIES[0]) == CATEGORIES[0]
