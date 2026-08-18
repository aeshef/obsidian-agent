"""Cascade routing and money verify gates."""
from __future__ import annotations

import asyncio

from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, ModelRole
from shared.llm import LLMResponse


@tool(category="balance", always=True)
async def sample_balance(ctx: AgentContext) -> str:
    """Balance figure from tools."""
    return "balance=92000"


def test_claimed_vs_tool_amounts():
    from shared.agent.verify import claimed_amounts, ungrounded_amounts

    k = chr(0x43A)
    rub = "\u20bd"
    assert claimed_amounts(f"left 140 000 {rub}") == [140000]
    assert claimed_amounts(f"spent 140{k} {rub}") == [140000]
    assert ungrounded_amounts(f"left 140000 {rub}", ["balance=92000"]) == [140000]
    assert ungrounded_amounts(f"left 92 000 {rub}", ["balance=92000"]) == []
    assert ungrounded_amounts("no figures", ["balance=92000"]) == []


def test_initial_role_unified_and_long(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.cascade import initial_role

    agent_dir = tmp_path / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "models.yaml").write_text(
        "cascade:\n  enabled: true\n  long_question_chars: 20\n"
        "  start_strong_domains: [unified]\n"
        "roles:\n  analyze:\n    model: flash\n  chat:\n    model: chat\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_models_config.cache_clear()
    assert initial_role("finance", "balance") is ModelRole.ANALYZE
    assert initial_role("unified", "balance") is ModelRole.CHAT
    assert initial_role("finance", "x" * 25) is ModelRole.CHAT
    agent_cfg.load_models_config.cache_clear()


def test_run_agent_blocks_ungrounded_amount(monkeypatch):
    from shared.agent import core as agent_core

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    rub = "\u20bd"
    reg = ToolRegistry()
    reg.register(sample_balance)
    ctx = AgentContext(user_id=1, domain="finance", question="balance?", system_prompt="s")

    async def _select(*args, **kwargs):
        return ["sample_balance"]

    monkeypatch.setattr(agent_core, "select_tools", _select)

    class _Router:
        def __init__(self) -> None:
            self.roles: list[str] = []

        def model_for(self, role: ModelRole) -> str:
            return "flash" if role is ModelRole.ANALYZE else "chat"

        async def chat_with_tools(self, *args, **kwargs):
            role = kwargs.get("role")
            self.roles.append(getattr(role, "value", str(role)))
            if len(self.roles) == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "sample_balance", "arguments": "{}"},
                        }
                    ],
                    raw={"model": "flash"},
                )
            return LLMResponse(
                text=f"left 140000 {rub}",
                tool_calls=[],
                raw={"model": "chat"},
            )

    router = _Router()
    out = asyncio.run(agent_core.run_agent(ctx, reg, router, max_iters=4))
    assert "140 000" in out or "140000" in out
    assert "92000" in out or "92 000" in out
    assert ModelRole.CHAT.value in router.roles


def test_run_agent_allows_grounded_amount(monkeypatch):
    from shared.agent import core as agent_core

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    rub = "\u20bd"
    reg = ToolRegistry()
    reg.register(sample_balance)
    ctx = AgentContext(user_id=1, domain="finance", question="balance?", system_prompt="s")

    async def _select(*args, **kwargs):
        return ["sample_balance"]

    monkeypatch.setattr(agent_core, "select_tools", _select)

    class _Router:
        async def chat_with_tools(self, *args, **kwargs):
            if not getattr(self, "n", 0):
                self.n = 1
                return LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "sample_balance", "arguments": "{}"},
                        }
                    ],
                    raw={},
                )
            return LLMResponse(text=f"left 92 000 {rub}", tool_calls=[], raw={})

    out = asyncio.run(agent_core.run_agent(ctx, reg, _Router(), max_iters=3))
    assert "92 000" in out
    assert "do not see" not in out.lower()
    assert "ungrounded" not in out.lower()


def test_run_agent_escalates_when_finance_skips_tools(monkeypatch):
    from shared.agent import core as agent_core

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    reg = ToolRegistry()
    reg.register(sample_balance)
    ctx = AgentContext(user_id=1, domain="finance", question="q", system_prompt="s")

    async def _select(*args, **kwargs):
        return ["sample_balance"]

    monkeypatch.setattr(agent_core, "select_tools", _select)

    class _Router:
        def __init__(self) -> None:
            self.roles: list[str] = []

        async def chat_with_tools(self, *args, **kwargs):
            role = kwargs.get("role")
            self.roles.append(getattr(role, "value", str(role)))
            if len(self.roles) == 1:
                return LLMResponse(text="guessing without tools", tool_calls=[], raw={})
            return LLMResponse(text="ok after escalate", tool_calls=[], raw={})

    router = _Router()
    out = asyncio.run(agent_core.run_agent(ctx, reg, router, max_iters=3))
    assert out == "ok after escalate"
    assert "chat" in router.roles


def test_format_progress_line_includes_model():
    from shared.telegram.agent_progress import format_progress_line

    plain = format_progress_line(1, ["get_balance"])
    modeled = format_progress_line(1, ["get_balance"], model="deepseek-v4-flash")
    assert "get_balance" in plain
    assert "get_balance" in modeled
    assert "deepseek-v4-flash" in modeled
    assert modeled != plain
