from planning_bot.services.kanban_agent import (
    filter_tasks,
    kanban_writes_allowed,
    resolve_column_name,
)
from planning_bot.core.config import BLOCKED_COLUMN, BACKLOG_COLUMN


def test_filter_tasks_column_and_priority():
    tasks = [
        {
            "title": "Deploy",
            "column": "🔄 В работе",
            "category": "работа",
            "priority": "высокий",
            "deadline": "2026-06-01",
            "completed": False,
            "task_id": "abc",
        },
        {
            "title": "Buy milk",
            "column": "📋 Бэклог",
            "category": "личное",
            "priority": "низкий",
            "deadline": None,
            "completed": False,
            "task_id": "def",
        },
    ]
    out = filter_tasks(tasks, column="работе", priority="высок")
    assert len(out) == 1
    assert out[0]["task_id"] == "abc"


def test_kanban_writes_default_off():
    assert kanban_writes_allowed() is False


def test_resolve_column_name_aliases():
    assert resolve_column_name("бэклог") == BACKLOG_COLUMN
    assert resolve_column_name("Заблокировано") == BLOCKED_COLUMN
    assert resolve_column_name(BLOCKED_COLUMN) == BLOCKED_COLUMN


def test_parse_sections_includes_task_id_metadata():
    from planning_bot.services.kanban_agent import _parse_sections

    content = (
        "---\nkanban-plugin: board\n---\n\n"
        "## 📋 Бэклог\n\n"
        "- [ ] Тест агента REAL\n"
        "\t#цель/личное #приоритет/низкий\n"
        "\t📅 Создано: 2026-06-01\n"
        "\t🆔 ID: c40b41a6\n\n"
        "- [ ] Другая задача\n"
        "\t🆔 ID: abcd1234\n\n"
        "## 📅 Ждёт даты\n\n"
    )
    sec = _parse_sections(content)
    blocks = sec.get("📋 Бэклог", [])
    assert any("c40b41a6" in b for b in blocks)
    assert any("abcd1234" in b for b in blocks)


def test_apply_move_finds_task_with_tab_metadata(tmp_path, monkeypatch):
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import _find_task_block, _parse_sections, apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(
        "---\nkanban-plugin: board\n---\n\n"
        "## 📋 Бэклог\n\n"
        "- [ ] Тест агента REAL\n"
        "\t#цель/личное #приоритет/низкий\n"
        "\t📅 Создано: 2026-06-01\n"
        "\t🆔 ID: deadbeef\n\n"
        "## 🚫 Заблокировано\n\n"
        "## ✅ Сделано\n\n"
        "%% kanban:settings\n```\n{}\n```\n%%\n",
        encoding="utf-8",
    )
    board = KanbanBoard(board_file)
    found = _find_task_block(_parse_sections(board.content), "deadbeef")
    assert found is not None
    out = apply_kanban_action(
        board,
        action="move",
        dry_run=False,
        task_id="deadbeef",
        column="Заблокировано",
        logger=None,
    )
    assert "OK" in out
    board.load()
    assert "deadbeef" in board.content
    assert "🚫 Заблокировано" in board.content


def test_sort_kanban_preserves_agent_task_block(tmp_path, monkeypatch):
    """После vault_maintenance-сортировки карточка с таб-метаданными и 🆔 ID не теряется."""
    from planning_bot.services.kanban_agent import _find_task_block, _parse_sections
    from planning_bot.tools.vault_maintenance.kanban_sort import sort_kanban_tasks

    board_file = tmp_path / "board.md"
    board_file.write_text(
        "---\nkanban-plugin: board\n---\n\n"
        "## 📋 Бэклог\n\n"
        "- [ ] Тест агента REAL\n"
        "\t#цель/личное #приоритет/низкий\n"
        "\t📅 Создано: 2026-06-01\n"
        "\t🆔 ID: deadbeef\n\n"
        "## 🚫 Заблокировано\n\n"
        "## ✅ Сделано\n\n"
        "%% kanban:settings\n```\n{}\n```\n%%\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FROM_SYNC", "1")
    assert sort_kanban_tasks(target_path=board_file) is True
    sec = _parse_sections(board_file.read_text(encoding="utf-8"))
    assert _find_task_block(sec, "deadbeef") is not None


def test_resolve_picks_newest_when_duplicate_titles():
    from planning_bot.services.kanban_agent import resolve_task_ids

    sections = {
        "📋 Бэклог": [
            "- [ ] Тест\n\t📅 Создано: 2026-06-01\n\t🆔 ID: aaaaaaaa\n",
            "- [ ] Тест\n\t📅 Создано: 2026-06-02\n\t🆔 ID: bbbbbbbb\n",
        ]
    }
    ids, note = resolve_task_ids(sections, title="Тест")
    assert ids == ["bbbbbbbb"]
    assert "Несколько" in note


def test_move_resolves_task_id_from_title_when_llm_passes_title_as_id(tmp_path, monkeypatch):
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(
        "---\nkanban-plugin: board\n---\n\n"
        "## 📋 Бэклог\n\n"
        "- [ ] Тест правок агента\n"
        "\t#цель/личное #приоритет/низкий\n"
        "\t🆔 ID: e7b33921\n\n"
        "## 🚫 Заблокировано\n\n"
        "## ✅ Сделано\n\n"
        "%% kanban:settings\n```\n{}\n```\n%%\n",
        encoding="utf-8",
    )
    board = KanbanBoard(board_file)
    out = apply_kanban_action(
        board,
        action="move",
        dry_run=False,
        task_id="Тест правок агента",
        column="Заблокировано",
        logger=None,
    )
    assert "OK" in out
    board.load()
    assert "e7b33921" in board.content
    assert "🚫 Заблокировано" in board.content


def test_apply_move_logs_task_moved(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(
        "---\nkanban-plugin: board\n---\n\n"
        "## 📋 Бэклог\n\n"
        "- [ ] Move me\n"
        "\t#цель/личное #приоритет/низкий\n"
        "\t🆔 ID: deadbeef\n\n"
        "## 🚫 Заблокировано\n\n"
        "## ✅ Сделано\n\n"
        "%% kanban:settings\n```\n{}\n```\n%%\n",
        encoding="utf-8",
    )
    board = KanbanBoard(board_file)
    logger = MagicMock()
    out = apply_kanban_action(
        board,
        action="move",
        dry_run=False,
        task_id="deadbeef",
        column="Заблокировано",
        logger=logger,
    )
    assert "OK" in out
    logger.log_task_moved.assert_called_once_with(
        "Move me",
        "📋 Бэклог",
        "🚫 Заблокировано",
        task_id="deadbeef",
        category="личное",
    )


def test_apply_complete_logs_task_completed(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(
        "---\nkanban-plugin: board\n---\n\n"
        "## 🚫 Заблокировано\n\n"
        "- [ ] Done me\n"
        "\t#цель/личное\n"
        "\t🆔 ID: deadbeef\n\n"
        "## ✅ Сделано\n\n"
        "%% kanban:settings\n```\n{}\n```\n%%\n",
        encoding="utf-8",
    )
    board = KanbanBoard(board_file)
    logger = MagicMock()
    out = apply_kanban_action(
        board,
        action="complete",
        task_id="deadbeef",
        logger=logger,
    )
    assert "OK" in out
    logger.log_task_completed.assert_called_once_with(
        "Done me", task_id="deadbeef", category="личное"
    )
    logger.log_task_moved.assert_not_called()


def test_apply_create_logs_priority(monkeypatch):
    from unittest.mock import MagicMock

    from planning_bot.services.kanban_agent import apply_kanban_action

    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board = MagicMock()
    board.add_task_to_backlog.return_value = "deadbeef"
    logger = MagicMock()
    out = apply_kanban_action(
        board,
        action="create",
        dry_run=False,
        title="Тест",
        category="личное",
        priority="низкий",
        logger=logger,
    )
    assert "deadbeef" in out
    logger.log_task_created.assert_called_once_with(
        "Тест", "личное", "низкий", task_id="deadbeef"
    )
