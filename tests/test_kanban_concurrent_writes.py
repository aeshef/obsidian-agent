from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from planning_bot.services.kanban import KanbanBoard
from tests.kanban_test_data import kanban_fixture


def test_parallel_add_tasks_all_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("KANBAN_AGENT_WRITES", "1")
    board_file = tmp_path / "board.md"
    board_file.write_text(kanban_fixture("board_move_deadbeef.md"), encoding="utf-8")
    board = KanbanBoard(board_file)

    def add_one(i: int) -> str:
        b = KanbanBoard(board_file)
        return b.add_task_to_backlog(f"parallel task {i}", "развитие", "средний")

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(add_one, range(12)))

    text = board_file.read_text(encoding="utf-8")
    for tid in ids:
        assert tid in text


def test_batch_add_tasks(tmp_path):
    board_file = tmp_path / "board.md"
    board_file.write_text(kanban_fixture("board_move_deadbeef.md"), encoding="utf-8")
    board = KanbanBoard(board_file)
    items = [(f"batch {i}", "развитие", "низкий") for i in range(5)]
    ids = board.add_tasks_to_backlog(items)
    assert len(ids) == 5
    text = board_file.read_text(encoding="utf-8")
    assert all(tid in text for tid in ids)
