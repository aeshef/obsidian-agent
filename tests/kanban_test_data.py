"""Kanban test helpers: fixture markdown + runtime strings from YAML/config."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from planning_bot.core.config import (
    BACKLOG_COLUMN,
    BLOCKED_COLUMN,
    CATEGORIES,
    IN_WORK_COLUMN,
    PRIORITIES,
    PRIORITY_ORDER,
)
from shared.vault_paths_config import folder, vault_file

_FIXTURES = Path(__file__).parent / "fixtures"
_KANBAN_FIXTURES = _FIXTURES / "kanban"


def kanban_fixture(name: str) -> str:
    return (_KANBAN_FIXTURES / name).read_text(encoding="utf-8")


def kanban_board_fixture_path(vault_root: Path) -> Path:
    return vault_root / folder("tasks") / vault_file("kanban_board")


@lru_cache(maxsize=1)
def kanban_test_strings() -> dict:
    data = yaml.safe_load((_FIXTURES / "test_strings.yaml").read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def kanban_strings(key: str) -> str:
    block = kanban_test_strings().get("kanban") or {}
    return str(block.get(key) or "")


__all__ = [
    "BACKLOG_COLUMN",
    "BLOCKED_COLUMN",
    "CATEGORIES",
    "IN_WORK_COLUMN",
    "PRIORITIES",
    "PRIORITY_ORDER",
    "kanban_board_fixture_path",
    "kanban_fixture",
    "kanban_strings",
]
