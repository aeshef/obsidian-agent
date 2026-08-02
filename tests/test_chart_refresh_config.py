"""Chart refresh allowlist matching (no builder subprocess)."""
from __future__ import annotations

from pathlib import Path

from shared.agent import chart_refresh as cr


def test_match_builder_keys(tmp_path: Path, monkeypatch):
    agent = tmp_path / "config" / "agent"
    agent.mkdir(parents=True)
    (agent / "platform.yaml").write_text(
        """
chart_refresh:
  enabled: 1
  builders:
    finance:
      script: finance_bot/scripts/build_finance_dashboard.py
    planning_activity:
      script: planning_bot/scripts/build_daily_task_activity_chart.py
    kanban_flow:
      script: planning_bot/scripts/build_kanban_flow_dashboard.py
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    from shared.agent.platform_config import load_platform_config

    load_platform_config.cache_clear()
    assert cr.match_builder_keys(builder="finance") == ["finance"]
    assert "planning_activity" in cr.match_builder_keys(family="planning")
    assert cr.match_builder_keys(builder="nope") == []
