"""Substantive task text guard (planning meta-only)."""
from __future__ import annotations

from planning_bot.services.kanban_parse import is_substantive_task_text


def test_substantive_task_text_rejects_meta_only():
    assert not is_substantive_task_text("заведи задачку", min_alnum=12, min_words=4)
    assert not is_substantive_task_text("➕ Добавить задачу", min_alnum=12, min_words=4)


def test_substantive_task_text_accepts_real_task():
    assert is_substantive_task_text(
        "Подготовить презентацию к встрече в пятницу, высокий приоритет",
        min_alnum=12,
        min_words=4,
    )
