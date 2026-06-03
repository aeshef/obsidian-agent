"""Regression: planning agent_tools must lazy-import service helpers (refactor 0229de9)."""
from __future__ import annotations

import inspect


def test_apply_kanban_task_imports_apply_kanban_action():
    from planning_bot.app import agent_tools

    src = inspect.getsource(agent_tools.apply_kanban_task)
    assert "from planning_bot.services.kanban_agent import apply_kanban_action" in src


def test_search_tasks_imports_filter_helpers():
    from planning_bot.app import agent_tools

    src = inspect.getsource(agent_tools.search_tasks)
    assert "filter_tasks" in src
    assert "format_task_list" in src


def test_get_kanban_done_preview_from_platform():
    from planning_bot.app import agent_tools

    src = inspect.getsource(agent_tools.get_kanban)
    assert "kanban_done_preview_max" in src
    assert "default=1000" in src
