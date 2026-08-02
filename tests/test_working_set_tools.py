"""Working-set pin/observe and tool-output extraction."""
from __future__ import annotations

import asyncio
from pathlib import Path

from shared.agent.types import AgentContext
from shared.memory import working_set as ws


def test_pin_and_observe_tool_output(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEMORY_WORKING_SET_PERSIST", "1")
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "mem.db"))
    ws._sqlite_ready = False
    ws.clear_working_set()
    ws.clear_working_set_pattern_cache()

    ws.pin_entity(1, "unified", "chart", "chart_finance_spend_png")
    got = ws.get_working_set(1, "unified")
    assert "chart:chart_finance_spend_png" in got.entities

    sample = (
        "Charts (2):\n"
        "chart_planning_activity_png [planning] ok mtime=2026-08-01T00:00:00+00:00 "
        "path=300_Dashboards/charts/a.png\n"
        "note path 700_Knowledge/demo.md mentioned\n"
    )
    ws.observe_tool_output(1, "unified", "list_vault_charts", sample)
    got = ws.get_working_set(1, "unified")
    assert any(e.startswith("chart:chart_planning_activity_png") for e in got.entities)
    assert any(n.endswith("demo.md") for n in got.notes)
    assert "tool:list_vault_charts" in got.entities


def test_working_set_agent_tools(tmp_path: Path, monkeypatch):
    from shared.agent import memory_tools as mt

    monkeypatch.setenv("MEMORY_WORKING_SET_PERSIST", "0")
    ws.clear_working_set()
    ctx = AgentContext(user_id=9, domain="finance", question="q", system_prompt="")
    out = asyncio.run(mt.pin_working_set(ctx, value="transport", kind="categories"))
    assert "transport" in out.lower() or "Pinned" in out or "Закреплено" in out
    listed = asyncio.run(mt.list_working_set(ctx))
    assert "transport" in listed.lower() or "categories" in listed.lower()
    cleared = asyncio.run(mt.clear_working_set_items(ctx, kind="categories"))
    assert cleared
