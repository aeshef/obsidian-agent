from __future__ import annotations

import os
from pathlib import Path

import yaml

from shared.capabilities.profile import MODULE_FINANCE, MODULE_PLANNING, CapabilityProfile
from shared.capabilities.vault_dashboard_scaffold import (
    build_scaffold_context,
    scaffold_vault_dashboards,
)


def _profile(modules: list[str]) -> CapabilityProfile:
    return CapabilityProfile(
        modules={m: True for m in modules},
        connectors={},
        sync_profile="full",
    )


def _patch_vault_paths(monkeypatch, doc: dict) -> None:
    from functools import lru_cache

    from shared import vault_paths_config as vpc

    vpc.vault_paths_config.cache_clear()

    @lru_cache(maxsize=1)
    def _cfg() -> dict:
        return doc

    monkeypatch.setattr(vpc, "vault_paths_config", _cfg)


def test_scaffold_main_dashboard_en_planning(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("AGENT_LOCALE", "en")
    _patch_vault_paths(
        monkeypatch,
        {
            "folders": {
                "tasks": "100_Tasks",
                "goals": "200_Goals",
                "dashboards": "300_Dashboards",
            },
            "dashboards": {"charts": "Charts", "data": "Data", "logs": "Logs"},
            "files": {
                "main_dashboard_md": "Main_Dashboard.md",
                "kanban_board": "Task_Board.md",
                "goals_template": "{year}_Goals.md",
                "goals_mapping_json": "goals_task_mapping.json",
                "calendar_dashboard_md": "Meetings.md",
                "calendar_json": "Calendar.json",
                "chart_daily_activity_md": "Daily_activity.md",
                "chart_completions_by_category_md": "Completed.md",
                "chart_open_pipeline_md": "Open_pipeline.md",
                "chart_deadline_horizon_md": "Deadlines.md",
                "chart_nutrition_md": "Nutrition.md",
                "nutrition_dashboard_md": "Nutrition.md",
            },
            "finance": {"dashboard_md": "Finance_Dashboard.md"},
        },
    )
    monkeypatch.setattr(
        "shared.capabilities.vault_dashboard_scaffold._kanban_schema",
        lambda: {
            "tag_prefixes": {"goal": "goal", "priority": "priority", "focus": "focus", "deadline": "deadline"},
            "categories": ["career", "study"],
            "category_order": {"career": 1, "study": 2},
            "priorities": ["high", "medium", "low"],
            "priority_order": {"high": 1, "medium": 2, "low": 3},
            "category_emojis": {"career": "💼"},
            "priority_emojis": {"high": "🔥"},
            "columns": ["Backlog", "Done"],
        },
    )

    prof = _profile([MODULE_PLANNING])
    written = scaffold_vault_dashboards(prof, vault, locale="en", force=True)
    assert written
    out = vault / "300_Dashboards" / "Main_Dashboard.md"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "#goal/" in text or 'TAG_GOAL = "goal"' in text
    assert "Finance_Dashboard" not in text
    assert "Daily_activity" in text or "Charts" in text


def test_scaffold_includes_finance_block(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))
    _patch_vault_paths(
        monkeypatch,
        {
            "folders": {"dashboards": "300_Dashboards", "goals": "200_Goals", "tasks": "100_Tasks"},
            "dashboards": {"charts": "Charts", "data": "Data", "logs": "Logs"},
                "files": {
                    "main_dashboard_md": "Main.md",
                    "goals_template": "{year}_Goals.md",
                    "kanban_board": "Board.md",
                    "calendar_dashboard_md": "Cal.md",
                    "calendar_json": "cal.json",
                    "goals_mapping_json": "map.json",
                    "chart_daily_activity_md": "a.md",
                    "chart_completions_by_category_md": "b.md",
                    "chart_open_pipeline_md": "c.md",
                    "chart_deadline_horizon_md": "d.md",
                    "chart_nutrition_md": "e.md",
                    "nutrition_dashboard_md": "n.md",
                },
            "finance": {"dashboard_md": "Finance.md", "graphs_finance": "Finance"},
        },
    )
    prof = _profile([MODULE_FINANCE])
    ctx = build_scaffold_context(prof, vault, locale="en")
    assert "Finance.md" in ctx["finance_dashboard"]
