"""Harness loop context: schema pin, clip, join-from-prior, working-set splice."""
from __future__ import annotations

import asyncio

from shared.agent.loop_context import (
    WORKING_SET_HEAD,
    clip_text,
    pick_join_series,
    splice_working_set_block,
)
from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import LOOP_TOOL_RESULTS_KEY, AgentContext


def test_clip_text_respects_budget():
    assert clip_text("abcd", 0) == "abcd"
    assert clip_text("abcd", 10) == "abcd"
    out = clip_text("abcdefghij", 4)
    assert out.endswith("…")
    assert len(out) == 4


def test_splice_working_set_replaces_block():
    sys0 = "base prompt\n\n" + WORKING_SET_HEAD + "\n- old"
    sys1 = splice_working_set_block(sys0, WORKING_SET_HEAD + "\n- new")
    assert "old" not in sys1
    assert "- new" in sys1
    assert sys1.startswith("base prompt")


def test_pick_join_series_skips_align_and_uses_last_two():
    picked = pick_join_series(
        [
            {"name": "get_spending_by_category", "content": "2026-08-12|2100\n2026-08-13|0\n"},
            {"name": "get_activity_events", "content": "2026-08-12|1\n2026-08-13|0\n"},
            {"name": "align_day_series", "content": "date | a | b\n2026-08-12 | 1 | 1\n"},
        ]
    )
    assert picked is not None
    a, b, la, lb = picked
    assert "2100" in a
    assert la == "get_spending_by_category"
    assert lb == "get_activity_events"
    assert "1" in b


def test_schema_pin_survives_budget(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.llm_classify import select_tools_llm
    from shared.agent.platform_config import load_platform_config

    agent_dir = tmp_path / "config" / "agent"
    (agent_dir / "prompts").mkdir(parents=True)
    (agent_dir / "prompts" / "tool_select_router.txt").write_text("pick tools", encoding="utf-8")
    (agent_dir / "tools.yaml").write_text(
        "domain_hints: {}\nschema_pin:\n  unified:\n    - align_day_series\n",
        encoding="utf-8",
    )
    (agent_dir / "platform.yaml").write_text(
        "agent:\n  max_tools_selected: 1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_tools_config.cache_clear()
    from shared.yaml_config import load_runtime_config

    load_runtime_config.cache_clear()
    load_platform_config.cache_clear()

    @tool(category="analytics")
    async def align_day_series(ctx: AgentContext) -> str:
        """join"""
        return "j"

    @tool(category="x")
    async def extra_one(ctx: AgentContext) -> str:
        """one"""
        return "1"

    @tool(category="x")
    async def extra_two(ctx: AgentContext) -> str:
        """two"""
        return "2"

    reg = ToolRegistry()
    for fn in (align_day_series, extra_one, extra_two):
        reg.register(fn)

    async def _fake(system, payload, *, label):
        return {"tools": ["extra_one", "extra_two"], "reason": "x"}

    monkeypatch.setattr("shared.agent.llm_classify._chat_json_classify", _fake)
    selected = asyncio.run(select_tools_llm("q", reg, domain="unified"))
    assert "align_day_series" in selected.offered
    assert "extra_one" in selected.picked
    assert "extra_two" not in selected.offered
    assert "extra_two" not in selected.picked
    agent_cfg.load_tools_config.cache_clear()
    load_platform_config.cache_clear()


def test_align_day_series_reads_prior_tool_bodies():
    from shared.agent.series_tools import align_day_series

    ctx = AgentContext(user_id=1, domain="unified", question="q", system_prompt="s")
    ctx.extras[LOOP_TOOL_RESULTS_KEY] = [
        {"name": "spend", "content": "2026-08-12|2100\n2026-08-14|4800\n"},
        {"name": "tasks", "content": "2026-08-12|1\n2026-08-14|2\n"},
    ]
    out = asyncio.run(align_day_series(ctx=ctx))
    assert "2026-08-12" in out
    assert "2100" in out or "2.1e" in out or "2100" in out.replace(" ", "")
    assert "shared=2" in out


def test_tally_event_shares_reads_prior_log_dump():
    from shared.agent.series_tools import tally_event_shares

    ctx = AgentContext(user_id=1, domain="unified", question="q", system_prompt="s")
    rows = []
    for i in range(8):
        rows.append(f"2026-08-01T10:{i*5:02d}:00\tAlpha\tfocus\t80\t")
    rows.append("2026-08-01T10:40:00\tBeta\tfocus\t80\t")
    ctx.extras[LOOP_TOOL_RESULTS_KEY] = [
        {"name": "get_interval_log", "content": "ts\tapp\tfocus\tbattery_pct\tsafari\n" + "\n".join(rows)},
    ]
    out = asyncio.run(tally_event_shares(ctx=ctx))
    assert "Alpha" in out
    assert "coverage:" in out
    assert "get_interval_log" in out


def test_select_tools_llm_greeting_is_chat_only(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.llm_classify import select_tools_llm

    agent_dir = tmp_path / "config" / "agent"
    (agent_dir / "prompts").mkdir(parents=True)
    (agent_dir / "prompts" / "tool_select_router.txt").write_text("pick tools", encoding="utf-8")
    (agent_dir / "tools.yaml").write_text(
        "schema_pin:\n  unified:\n    - align_day_series\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_tools_config.cache_clear()
    from shared.yaml_config import load_runtime_config

    load_runtime_config.cache_clear()

    @tool(category="analytics")
    async def align_day_series(ctx: AgentContext) -> str:
        """join"""
        return "j"

    @tool(category="balance")
    async def get_balance(ctx: AgentContext) -> str:
        """balance"""
        return "b"

    reg = ToolRegistry()
    reg.register(align_day_series)
    reg.register(get_balance)

    async def _fake(system, payload, *, label):
        return {"tools": [], "reason": "chat"}

    monkeypatch.setattr("shared.agent.llm_classify._chat_json_classify", _fake)
    selected = asyncio.run(select_tools_llm("hey", reg, domain="unified"))
    assert selected.picked == []
    assert selected.offered == []
    agent_cfg.load_tools_config.cache_clear()
    load_runtime_config.cache_clear()


def test_select_tools_llm_picked_pin_name_counts(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.llm_classify import select_tools_llm

    agent_dir = tmp_path / "config" / "agent"
    (agent_dir / "prompts").mkdir(parents=True)
    (agent_dir / "prompts" / "tool_select_router.txt").write_text("pick tools", encoding="utf-8")
    (agent_dir / "tools.yaml").write_text(
        "schema_pin:\n  default:\n    - align_day_series\n  unified:\n    - get_balance\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_tools_config.cache_clear()
    from shared.yaml_config import load_runtime_config

    load_runtime_config.cache_clear()

    @tool(category="analytics")
    async def align_day_series(ctx: AgentContext) -> str:
        """join"""
        return "j"

    @tool(category="balance")
    async def get_balance(ctx: AgentContext) -> str:
        """balance"""
        return "b"

    reg = ToolRegistry()
    reg.register(align_day_series)
    reg.register(get_balance)

    async def _fake(system, payload, *, label):
        return {"tools": ["get_balance"], "reason": "data"}

    monkeypatch.setattr("shared.agent.llm_classify._chat_json_classify", _fake)
    selected = asyncio.run(select_tools_llm("balance?", reg, domain="unified"))
    assert "get_balance" in selected.picked
    assert "align_day_series" in selected.offered
    agent_cfg.load_tools_config.cache_clear()
    load_runtime_config.cache_clear()


def test_select_tools_passes_dialogue_context(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.llm_classify import select_tools_llm
    from shared.agent.types import AgentMessage
    from shared.yaml_config import load_runtime_config

    agent_dir = tmp_path / "config" / "agent"
    (agent_dir / "prompts").mkdir(parents=True)
    (agent_dir / "prompts" / "tool_select_router.txt").write_text("pick tools", encoding="utf-8")
    (agent_dir / "tools.yaml").write_text("domain_hints: {}\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_tools_config.cache_clear()
    load_runtime_config.cache_clear()

    @tool(category="charts")
    async def send_vault_charts(ctx: AgentContext) -> str:
        """send"""
        return "s"

    reg = ToolRegistry()
    reg.register(send_vault_charts)
    captured: dict = {}

    async def _fake(system, payload, *, label):
        captured.update(payload)
        return {"tools": ["send_vault_charts"]}

    monkeypatch.setattr("shared.agent.llm_classify._chat_json_classify", _fake)
    history = [AgentMessage(role="assistant", content="Нашёл график трат, отправить?")]
    selected = asyncio.run(
        select_tools_llm("отправляй", reg, domain="unified", history=history)
    )
    assert "send_vault_charts" in selected.picked
    assert "график" in captured.get("dialogue_context", "")
    agent_cfg.load_tools_config.cache_clear()
    load_runtime_config.cache_clear()
