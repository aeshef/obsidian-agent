"""Tests for kanban archive and merged corpus."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from planning_bot.core.config import DONE_COLUMN, KANBAN_COLUMNS
from planning_bot.services.kanban_format import task_created_line
from planning_bot.tools.vault_maintenance.kanban_state import get_kanban_state
from tests.kanban_test_data import kanban_fixture


def _minimal_vault_paths() -> dict:
    return {
        "folders": {
            "tasks": "100_Tasks",
            "goals": "200_Goals",
            "dashboards": "300_Dashboards",
            "routines": "400_Routines",
            "handwritten": "600_Handwritten",
            "archive": "600_Archive",
            "automation": "800_Automation",
        },
        "dashboards": {"logs": "Logs", "charts": "Charts", "data": "Data"},
        "files": {
            "kanban_board": "📋 Task_Board.md",
            "kanban_archive_board": "📦 Closed_Tasks.md",
            "goals_template": "🎯 {year}_Goals.md",
            "action_log_prefix": "📊 Action_Logs_",
            "goals_mapping_json": "goals_task_mapping.json",
            "completed_tasks_soc_json": "completed_tasks_soc.json",
            "calendar_txt": "Calendar.txt",
            "calendar_json": "Calendar.json",
            "calendar_dashboard_md": "Cal.md",
            "calendar_week_analytics_json": "cal_week.json",
            "calendar_insights_cache_json": "cal_insights.json",
            "chart_deadline_horizon_png": "d.png",
            "chart_deadline_horizon_md": "d.md",
            "chart_daily_activity_png": "a.png",
            "chart_daily_activity_md": "a.md",
            "chart_completions_by_category_png": "c.png",
            "chart_completions_by_category_md": "c.md",
            "chart_open_pipeline_png": "o.png",
            "chart_open_pipeline_md": "o.md",
            "chart_calendar_week_png": "w.png",
            "chart_calendar_sections_png": "s.png",
            "chart_calendar_sections_md": "s.md",
            "open_tasks_history_json": "open.json",
            "chart_nutrition_png": "n.png",
            "chart_nutrition_md": "n.md",
            "chart_health_trends_png": "ht.png",
            "chart_health_trends_md": "ht.md",
            "chart_health_correlations_png": "hc.png",
            "chart_health_correlations_md": "hc.md",
            "chart_cross_correlations_png": "xc.png",
            "chart_cross_correlations_md": "xc.md",
            "chart_cross_tasks_steps_png": "xs.png",
            "chart_cross_tasks_steps_md": "xs.md",
            "chart_cross_tasks_spending_png": "xsp.png",
            "chart_cross_tasks_spending_md": "xsp.md",
            "main_dashboard_md": "main.md",
            "health_dashboard_md": "health.md",
            "nutrition_dashboard_md": "health.md",
            "system_audit_report_md": "audit_sys.md",
            "vault_audit_report_md": "audit_vault.md",
            "reflection_weekly_file": "ref_{date}.md",
            "routines_calendar_subdir": "routines/",
            "routines_stats_md": "routines_stats.md",
            "signals_subdir": "signals/",
            "signals_config_yaml": "signals.yaml",
            "signals_history_md": "signals_history.md",
        },
        "paths": {
            "knowledge_attachments": "_att",
            "knowledge_hubs": "_hubs",
            "reflection_subdir": "Reflection",
            "actions_mac": "Mac",
            "actions_iphone": "IPhone",
            "context_today_json": "context_today.json",
            "context_week_json": "context_week.json",
            "iphone_today_json": "iphone_today.json",
            "iphone_week_json": "iphone_week.json",
            "cross_daily_features_json": "cross.json",
            "agent_subdir": "Agent",
            "templates_clones": "Templates/Clones",
        },
        "finance": {
            "dashboard_md": "Finance.md",
            "graphs_finance": "Finance",
            "chart_daily_categories_png": "f.png",
            "meta": "meta",
            "portfolio_log": "p.log",
            "portfolio_cache": "p.md",
        },
        "planning": {"graphs_planning": "Planning"},
        "health": {"graphs_health": "Health"},
        "cross": {"graphs_cross": "Cross"},
    }


@pytest.fixture
def kanban_archive_vault(tmp_path: Path, monkeypatch) -> Path:
    vault = tmp_path / "vault"
    tasks = vault / "100_Tasks"
    dash = vault / "300_Dashboards"
    logs = dash / "Logs"
    tasks.mkdir(parents=True)
    logs.mkdir(parents=True)

    active = tasks / "📋 Task_Board.md"
    archive = tasks / "📦 Closed_Tasks.md"

    header = kanban_fixture("board_parse_sections.md").split("##")[0]
    done_col = DONE_COLUMN or "✅ Done"
    backlog = KANBAN_COLUMNS[0] if KANBAN_COLUMNS else "📋 Backlog"
    month_prefix = date.today().strftime("%Y-%m")

    month_line = task_created_line(f"{month_prefix}-02")

    active.write_text(
        f"{header}\n\n## {backlog}\n\n- [ ] Open task\n\t🆔 ID: aaa11111\n\n"
        f"## {done_col}\n\n"
        f"- [x] Old done\n\t{task_created_line('2024-01-15')}\n\t🆔 ID: deadbeef\n\n"
        f"- [x] This month\n\t{month_line}\n\t🆔 ID: bb222222\n\n",
        encoding="utf-8",
    )
    archive.write_text(
        f"# Closed\n\n## {done_col} · 2024-01\n\n"
        f"- [x] Archived only\n\t🆔 ID: cc333333\n\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("FROM_SYNC", "1")
    monkeypatch.setenv("AGENT_LOCALE", "en")

    from functools import lru_cache
    from shared import vault_paths_config as vp

    @lru_cache(maxsize=1)
    def _fake_vault_paths():
        return _minimal_vault_paths()

    vp.vault_paths_config.cache_clear()
    monkeypatch.setattr(vp, "vault_paths_config", _fake_vault_paths)

    from shared.kanban_paths import kanban_archive_file_configured

    kanban_archive_file_configured.cache_clear()

    import planning_bot.core.config as planning_config

    planning_config.VAULT_PATH = vault
    planning_config.KANBAN_FILE = active
    planning_config.LOGS_DIR = dash
    planning_config.ACTION_LOGS_DIR = logs

    return vault


def test_get_kanban_state_merges_archive(kanban_archive_vault: Path):
    state = get_kanban_state()
    assert "aaa11111" in state
    assert "deadbeef" in state
    assert "cc333333" in state
    assert state["cc333333"] == DONE_COLUMN


def test_archive_moves_old_done_tasks(kanban_archive_vault: Path, monkeypatch):
    from planning_bot.core.config import KANBAN_FILE
    from planning_bot.tools.vault_maintenance.kanban_archive import archive_done_tasks

    monkeypatch.setattr(
        "planning_bot.tools.vault_maintenance.kanban_archive._completion_dates_from_logs",
        lambda: {"deadbeef": date(2024, 1, 20)},
    )

    ok = archive_done_tasks()
    assert ok is True

    active_text = KANBAN_FILE.read_text(encoding="utf-8")
    assert "deadbeef" not in active_text
    assert "bb222222" in active_text

    archive_path = kanban_archive_vault / "100_Tasks" / "📦 Closed_Tasks.md"
    archive_text = archive_path.read_text(encoding="utf-8")
    assert "deadbeef" in archive_text

    state = get_kanban_state()
    assert state["deadbeef"] == DONE_COLUMN
    assert state["bb222222"] == DONE_COLUMN
