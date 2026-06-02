"""Kanban schema must define columns — empty list breaks vault_maintenance sort."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_kanban_schema_has_columns():
    from planning_bot.core.config import KANBAN_COLUMNS, DONE_COLUMN

    assert len(KANBAN_COLUMNS) >= 5
    assert DONE_COLUMN == "✅ Сделано"
    assert "📋 Бэклог" in KANBAN_COLUMNS


def test_kanban_schema_merges_columns_from_example(tmp_path: Path, monkeypatch):
    """Local yaml without columns still gets them from .example (no code fallback)."""
    cfg_dir = tmp_path / "planning_bot" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "kanban_schema.yaml.example").write_text(
        "columns:\n  - ColA\n  - ColB\ncategories: []\n",
        encoding="utf-8",
    )
    (cfg_dir / "kanban_schema.yaml").write_text("categories:\n  - x\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    from shared.yaml_config import load_merged_config

    merged = load_merged_config(str(cfg_dir), "kanban_schema")
    assert merged.get("columns") == ["ColA", "ColB"]


def test_sort_kanban_aborts_without_columns(monkeypatch, tmp_path: Path):
    from planning_bot.tools.vault_maintenance import sort_kanban_tasks

    monkeypatch.setattr(
        "planning_bot.tools.vault_maintenance.kanban_sort.KANBAN_COLUMNS",
        [],
    )
    monkeypatch.setattr(
        "planning_bot.tools.vault_maintenance.kanban_sort.DONE_COLUMN",
        "",
    )
    board = tmp_path / "board.md"
    board.write_text("---\n\nkanban-plugin: board\n\n---\n\n## 📋 Бэклог\n\n", encoding="utf-8")
    assert sort_kanban_tasks(target_path=board) is False
