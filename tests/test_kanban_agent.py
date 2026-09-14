from __future__ import annotations

from planning_bot.core.config import BLOCKED_COLUMN, BACKLOG_COLUMN, CATEGORIES, IN_WORK_COLUMN, PRIORITIES
from planning_bot.services.kanban_agent import (
    filter_tasks,
    kanban_writes_allowed,
    resolve_column_name,
)
from tests.kanban_test_data import kanban_fixture, kanban_strings


def test_filter_tasks_created_range_and_sort():
    tasks = [
        {
            "title": "Old backlog",
            "column": BACKLOG_COLUMN,
            "category": CATEGORIES[0],
            "priority": PRIORITIES[2],
            "deadline": None,
            "created_date": "2025-12-01",
            "completed": False,
            "task_id": "old1",
        },
        {
            "title": "New backlog",
            "column": BACKLOG_COLUMN,
            "category": CATEGORIES[0],
            "priority": PRIORITIES[2],
            "deadline": None,
            "created_date": "2026-06-01",
            "completed": False,
            "task_id": "new1",
        },
    ]
    backlog_key = BACKLOG_COLUMN.split()[-1]
    out = filter_tasks(tasks, column=backlog_key, sort_by="created_asc")
    assert [t["task_id"] for t in out] == ["old1", "new1"]
    out2 = filter_tasks(tasks, created_to="2026-01-01")
    assert len(out2) == 1 and out2[0]["task_id"] == "old1"


def test_filter_tasks_column_and_priority():
    in_work_key = IN_WORK_COLUMN.split()[-1]
    high_key = PRIORITIES[0][:4]
    tasks = [
        {
            "title": "Deploy",
            "column": IN_WORK_COLUMN,
            "category": CATEGORIES[0],
            "priority": PRIORITIES[0],
            "deadline": "2026-06-01",
            "completed": False,
            "task_id": "abc",
        },
        {
            "title": "Buy milk",
            "column": BACKLOG_COLUMN,
            "category": CATEGORIES[3] if len(CATEGORIES) > 3 else CATEGORIES[1],
            "priority": PRIORITIES[2],
            "deadline": None,
            "completed": False,
            "task_id": "def",
        },
    ]
    out = filter_tasks(tasks, column=in_work_key, priority=high_key)
    assert len(out) == 1
    assert out[0]["task_id"] == "abc"


def test_kanban_writes_default_off(monkeypatch):
    monkeypatch.delenv("KANBAN_AGENT_WRITES", raising=False)
    assert kanban_writes_allowed() is False


def test_resolve_column_name_aliases():
    backlog_key = BACKLOG_COLUMN.replace("📋", "").strip().split()[-1].lower()
    assert resolve_column_name(backlog_key) == BACKLOG_COLUMN
    blocked_key = BLOCKED_COLUMN.split()[-1]
    assert resolve_column_name(blocked_key) == BLOCKED_COLUMN
    assert resolve_column_name(BLOCKED_COLUMN) == BLOCKED_COLUMN


def test_parse_sections_includes_task_id_metadata():
    from planning_bot.services.kanban_agent import _parse_sections

    sec = _parse_sections(kanban_fixture("board_parse_sections.md"))
    blocks = sec.get(BACKLOG_COLUMN, [])
    assert any("c40b41a6" in b for b in blocks)
    assert any("abcd1234" in b for b in blocks)


def test_apply_move_finds_task_with_tab_metadata(tmp_path, monkeypatch):
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import _find_task_block, _parse_sections, apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(kanban_fixture("board_move_deadbeef.md"), encoding="utf-8")
    board = KanbanBoard(board_file)
    board.load()
    found = _find_task_block(_parse_sections(board.content), "deadbeef")
    assert found is not None
    blocked_key = BLOCKED_COLUMN.split()[-1]
    out = apply_kanban_action(
        board,
        action="move",
        dry_run=False,
        task_id="deadbeef",
        column=blocked_key,
        logger=None,
    )
    assert "OK" in out
    board.load()
    assert "deadbeef" in board.content
    assert BLOCKED_COLUMN in board.content


def test_sort_kanban_preserves_agent_task_block(tmp_path, monkeypatch):
    """After vault_maintenance sort, task block with tab metadata and ID is preserved."""
    from planning_bot.services.kanban_agent import _find_task_block, _parse_sections
    from planning_bot.tools.vault_maintenance.kanban_sort import sort_kanban_tasks

    board_file = tmp_path / "board.md"
    board_file.write_text(kanban_fixture("board_move_deadbeef.md"), encoding="utf-8")
    monkeypatch.setenv("FROM_SYNC", "1")
    assert sort_kanban_tasks(target_path=board_file) is True
    sec = _parse_sections(board_file.read_text(encoding="utf-8"))
    assert _find_task_block(sec, "deadbeef") is not None


def test_resolve_picks_newest_when_duplicate_titles():
    from planning_bot.services.kanban_agent import _parse_sections, resolve_task_ids

    title = kanban_strings("task_title_test")
    sections = _parse_sections(kanban_fixture("board_duplicate_titles.md"))
    ids, note = resolve_task_ids(sections, title=title)
    assert ids == ["bbbbbbbb"]
    assert kanban_strings("multiple_match_prefix") in note


def test_move_resolves_task_id_from_title_when_llm_passes_title_as_id(tmp_path, monkeypatch):
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(kanban_fixture("board_move_by_title.md"), encoding="utf-8")
    board = KanbanBoard(board_file)
    title = kanban_strings("task_title_agent_edits")
    blocked_key = BLOCKED_COLUMN.split()[-1]
    out = apply_kanban_action(
        board,
        action="move",
        dry_run=False,
        task_id=title,
        column=blocked_key,
        logger=None,
    )
    assert "OK" in out
    board.load()
    assert "e7b33921" in board.content
    assert BLOCKED_COLUMN in board.content


def test_apply_move_logs_task_moved(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(kanban_fixture("board_log_move.md"), encoding="utf-8")
    board = KanbanBoard(board_file)
    logger = MagicMock()
    blocked_key = BLOCKED_COLUMN.split()[-1]
    out = apply_kanban_action(
        board,
        action="move",
        dry_run=False,
        task_id="deadbeef",
        column=blocked_key,
        logger=logger,
    )
    assert "OK" in out
    personal = kanban_strings("personal_category")
    logger.log_task_moved.assert_called_once_with(
        "Move me",
        BACKLOG_COLUMN,
        BLOCKED_COLUMN,
        task_id="deadbeef",
        category=personal,
    )


def test_apply_complete_logs_task_completed(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(kanban_fixture("board_log_complete.md"), encoding="utf-8")
    board = KanbanBoard(board_file)
    logger = MagicMock()
    out = apply_kanban_action(
        board,
        action="complete",
        task_id="deadbeef",
        logger=logger,
    )
    assert "OK" in out
    personal = kanban_strings("personal_category")
    logger.log_task_completed.assert_called_once_with(
        "Done me", task_id="deadbeef", category=personal
    )
    logger.log_task_moved.assert_not_called()


def test_apply_create_logs_priority(monkeypatch):
    from unittest.mock import MagicMock

    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board = MagicMock()
    board.add_task_to_backlog.return_value = "deadbeef"
    logger = MagicMock()
    title = kanban_strings("task_title_test")
    personal = kanban_strings("personal_category")
    low = PRIORITIES[2]
    out = apply_kanban_action(
        board,
        action="create",
        dry_run=False,
        title=title,
        category=personal,
        priority=low,
        logger=logger,
    )
    from planning_bot.services.kanban_format import normalize_category

    assert "deadbeef" in out
    logger.log_task_created.assert_called_once_with(
        title, normalize_category(personal), low, task_id="deadbeef"
    )


def test_create_with_deadline_round_trips_and_logs(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(f"## {BACKLOG_COLUMN}\n\n", encoding="utf-8")
    board = KanbanBoard(board_file)
    logger = MagicMock()
    out = apply_kanban_action(
        board, action="create", title="Submit report", deadline="2026-09-25", logger=logger
    )
    assert "deadline=2026-09-25" in out
    from planning_bot.services.kanban_parse import metadata_from_block
    raw = board_file.read_text(encoding="utf-8")
    meta = metadata_from_block(raw)
    assert meta["deadline"] == "2026-09-25"
    assert "#дедлайн/2026-09-25" in raw
    logger.log_task_created.assert_called_once_with(
        "Submit report", meta["category"], meta["priority"],
        task_id=meta["task_id"], deadline="2026-09-25",
    )


def test_create_without_deadline_does_not_add_tag(monkeypatch, tmp_path):
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(f"## {BACKLOG_COLUMN}\n\n", encoding="utf-8")
    board = KanbanBoard(board_file)
    out = apply_kanban_action(board, action="create", title="Untimed")
    assert "deadline=" not in out
    assert "#дедлайн/" not in board_file.read_text(encoding="utf-8")


def test_create_invalid_deadline_rejected_before_write(monkeypatch, tmp_path):
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    original = f"## {BACKLOG_COLUMN}\n\n"
    board_file.write_text(original, encoding="utf-8")
    board = KanbanBoard(board_file)
    for invalid in ("2026-02-30", "2026-09-25T10:00"):
        out = apply_kanban_action(board, action="create", title="Bad", deadline=invalid)
        assert invalid in out
        assert board_file.read_text(encoding="utf-8") == original


def test_batch_create_with_deadline(monkeypatch, tmp_path):
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(f"## {BACKLOG_COLUMN}\n\n", encoding="utf-8")
    board = KanbanBoard(board_file)
    apply_kanban_action(board, action="create", titles=["One", "Two"], deadline="2026-09-25")
    assert board_file.read_text(encoding="utf-8").count("#дедлайн/2026-09-25") == 2
