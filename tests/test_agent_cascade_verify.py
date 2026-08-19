"""Cascade routing and tool-grounded number verify (policy in models.yaml)."""
from __future__ import annotations

import asyncio

from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, ModelRole
from shared.llm import LLMResponse


@tool(category="balance", always=True)
async def sample_balance(ctx: AgentContext) -> str:
    """Balance figure from tools."""
    return "balance=92000"


def test_rewrite_is_meta_uses_markers(monkeypatch):
    from shared.agent.verify import rewrite_is_meta

    monkeypatch.setattr(
        "shared.agent.verify.rewrite_meta_markers",
        lambda: ["tool data", "these amounts"],
    )
    assert rewrite_is_meta("The tool data does not contain these amounts: 70 000.")
    assert not rewrite_is_meta("Venue Alpha ran three shows this week.")


def test_verify_draft_skips_when_no_tools():
    from shared.agent.verify import verify_draft

    out = asyncio.run(verify_draft("hello 140000", []))
    assert out.ok is True
    assert out.rewrite == ""


def test_verify_draft_uses_llm_rewrite(monkeypatch):
    from shared.agent.verify import verify_draft

    async def _fake(answer, tools):
        return {"ok": False, "rewrite": "left 92 000"}

    monkeypatch.setattr("shared.agent.verify.verify_enabled", lambda: True)
    monkeypatch.setattr("shared.agent.llm_classify.verify_grounding_llm", _fake)
    out = asyncio.run(verify_draft("left 140000", ["balance=92000"]))
    assert out.ok is False
    assert "92 000" in out.rewrite


def test_verify_draft_drops_audit_rewrite(monkeypatch):
    from shared.agent.verify import verify_draft

    async def _fake(answer, tools):
        return {
            "ok": False,
            "rewrite": "The tool data does not contain these amounts: 70 000. What the tools returned: venue.",
        }

    monkeypatch.setattr("shared.agent.verify.verify_enabled", lambda: True)
    monkeypatch.setattr(
        "shared.agent.verify.rewrite_meta_markers",
        lambda: ["tool data", "these amounts", "what the tools returned"],
    )
    monkeypatch.setattr("shared.agent.llm_classify.verify_grounding_llm", _fake)
    out = asyncio.run(verify_draft("tickets 70 000", ["venue Alpha, three shows"]))
    assert out.ok is False
    assert out.rewrite == ""


def test_run_agent_uses_verify_rewrite(monkeypatch):
    from shared.agent import core as agent_core
    from shared.agent.verify import VerifyVerdict

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    rub = chr(0x20BD)
    reg = ToolRegistry()
    reg.register(sample_balance)
    ctx = AgentContext(user_id=1, domain="finance", question="balance?", system_prompt="s")

    async def _select(*args, **kwargs):
        return ["sample_balance"]

    async def _verify(text, bodies):
        return VerifyVerdict(ok=False, rewrite="left 92 000")

    monkeypatch.setattr(agent_core, "select_tools", _select)
    monkeypatch.setattr(agent_core, "verify_draft", _verify)

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
            return LLMResponse(text=f"left 140000 {rub}", tool_calls=[], raw={})

    out = asyncio.run(agent_core.run_agent(ctx, reg, _Router(), max_iters=3))
    assert "92 000" in out
    assert "140000" not in out.replace(" ", "")


def test_initial_role_unified_and_long(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.cascade import initial_role

    agent_dir = tmp_path / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "models.yaml").write_text(
        "cascade:\n  enabled: true\n  cheap_role: analyze\n  strong_role: chat\n"
        "  start_strong:\n    min_question_chars: 20\n    domains: [unified]\n"
        "roles:\n  analyze:\n    model: flash\n  chat:\n    model: chat\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_models_config.cache_clear()
    assert initial_role("finance", "balance") is ModelRole.ANALYZE
    assert initial_role("unified", "balance") is ModelRole.CHAT
    assert initial_role("finance", "x" * 25) is ModelRole.CHAT
    agent_cfg.load_models_config.cache_clear()


def test_initial_role_cross_domain_not_all_unified(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.cascade import initial_role
    from shared.yaml_config import load_merged_config

    agent_dir = tmp_path / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "models.yaml").write_text(
        "cascade:\n  enabled: true\n  cheap_role: analyze\n  strong_role: chat\n"
        "  start_strong:\n    min_question_chars: 5000\n    domains: []\n"
        "    cross_domain: true\n",
        encoding="utf-8",
    )
    (agent_dir / "routing.yaml").write_text(
        "host:\n  cross_domain_escalation:\n    finance_pattern: food|spend\n"
        "    planning_pattern: task|kanban\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_models_config.cache_clear()
    agent_cfg.load_routing_config.cache_clear()
    load_merged_config.cache_clear()
    assert initial_role("unified", "balance please") is ModelRole.ANALYZE
    assert initial_role("unified", "food spend vs closed tasks") is ModelRole.CHAT
    agent_cfg.load_models_config.cache_clear()
    agent_cfg.load_routing_config.cache_clear()
    load_merged_config.cache_clear()


def test_initial_role_disabled(monkeypatch, tmp_path):
    from shared.agent import config as agent_cfg
    from shared.agent.cascade import initial_role

    agent_dir = tmp_path / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "models.yaml").write_text(
        "cascade:\n  enabled: false\n  start_strong:\n    domains: [unified]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent_cfg.load_models_config.cache_clear()
    assert initial_role("unified", "x" * 500) is ModelRole.ANALYZE
    agent_cfg.load_models_config.cache_clear()


def test_run_agent_allows_grounded_amount(monkeypatch):
    from shared.agent import core as agent_core
    from shared.agent.verify import VerifyVerdict

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    rub = chr(0x20BD)
    reg = ToolRegistry()
    reg.register(sample_balance)
    ctx = AgentContext(user_id=1, domain="finance", question="balance?", system_prompt="s")

    async def _select(*args, **kwargs):
        return ["sample_balance"]

    async def _verify(text, bodies):
        return VerifyVerdict(ok=True)

    monkeypatch.setattr(agent_core, "select_tools", _select)
    monkeypatch.setattr(agent_core, "verify_draft", _verify)

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


def test_run_agent_chat_only_does_not_require_tools(monkeypatch):
    from shared.agent import core as agent_core
    from shared.agent.types import ToolSelection

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    @tool(category="analytics")
    async def align_day_series(ctx: AgentContext) -> str:
        """join"""
        return "j"

    reg = ToolRegistry()
    reg.register(align_day_series)
    ctx = AgentContext(user_id=1, domain="unified", question="hey", system_prompt="s")

    async def _select(*args, **kwargs):
        return ToolSelection(offered=["align_day_series"], picked=[])

    monkeypatch.setattr(agent_core, "select_tools", _select)

    class _Router:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def chat_with_tools(self, messages, tools, **kwargs):
            self.calls.append({"tools": tools, "tool_choice": kwargs.get("tool_choice")})
            return LLMResponse(text="doing fine", tool_calls=[], raw={})

    router = _Router()
    out = asyncio.run(agent_core.run_agent(ctx, reg, router, max_iters=3))
    assert out == "doing fine"
    assert router.calls[0]["tool_choice"] == "auto"
    assert router.calls[0]["tools"] == []


def test_run_agent_empty_response_escalates(monkeypatch):
    from shared.agent import core as agent_core

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    reg = ToolRegistry()
    ctx = AgentContext(user_id=1, domain="unified", question="hey", system_prompt="s")

    async def _select(*args, **kwargs):
        return []

    monkeypatch.setattr(agent_core, "select_tools", _select)

    class _Router:
        def __init__(self) -> None:
            self.roles: list[str] = []

        async def chat_with_tools(self, *args, **kwargs):
            role = kwargs.get("role")
            self.roles.append(getattr(role, "value", str(role)))
            if len(self.roles) == 1:
                return LLMResponse(text=None, tool_calls=[], raw={})
            return LLMResponse(text="hello", tool_calls=[], raw={})

    router = _Router()
    out = asyncio.run(agent_core.run_agent(ctx, reg, router, max_iters=3))
    assert out == "hello"
    assert "chat" in router.roles
