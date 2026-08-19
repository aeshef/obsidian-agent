"""Answer-guard: leaked tool prose and incomplete fetch (not domain-specific)."""
from __future__ import annotations

import asyncio

from shared.agent.answer_guard import (
    coerce_text_tool_calls,
    looks_like_incomplete_fetch,
    looks_like_tool_narration,
    strip_tool_narration,
)
from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext
from shared.llm import LLMResponse


def test_invoking_tool_is_narration_and_parses():
    text = (
        'Invoking tool get_interval_log with '
        '{"from_ts": "2026-07-01T00:00:00+03:00", "to_ts": "2026-07-31T23:59:59+03:00"} ...'
    )
    assert looks_like_tool_narration(text)
    calls = coerce_text_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_interval_log"
    assert "2026-07-01" in calls[0]["function"]["arguments"]
    assert strip_tool_narration(text) == ""


def test_promised_fetch_short_is_incomplete():
    assert looks_like_incomplete_fetch(
        "Возьму данные за период и посчитаю доли."
    )
    assert not looks_like_incomplete_fetch(
        "Доля Alpha 44%.\n\n| app | share |\n| Alpha | 44% |\n| Beta | 21% |\n"
    )


def test_run_agent_executes_text_tool_call(monkeypatch):
    from shared.agent import core as agent_core
    from shared.agent.verify import VerifyVerdict

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    @tool(category="context")
    async def get_interval_log(ctx: AgentContext, from_ts: str = "", to_ts: str = "") -> str:
        """interval log"""
        return "value\tcount\tcount_share\thours\thour_share\tdays\nAlpha\t10\t80.0%\t1.0\t80.0%\t1"

    reg = ToolRegistry()
    reg.register(get_interval_log)
    ctx = AgentContext(user_id=1, domain="unified", question="shares?", system_prompt="s")

    async def _select(*args, **kwargs):
        return ["get_interval_log"]

    async def _verify(text, bodies):
        return VerifyVerdict(ok=True)

    monkeypatch.setattr(agent_core, "select_tools", _select)
    monkeypatch.setattr(agent_core, "verify_draft", _verify)

    class _Router:
        async def chat_with_tools(self, *args, **kwargs):
            if not getattr(self, "n", 0):
                self.n = 1
                return LLMResponse(
                    text=(
                        'Invoking tool get_interval_log with '
                        '{"from_ts": "2026-08-01", "to_ts": "2026-08-19"}'
                    ),
                    tool_calls=[],
                    raw={},
                )
            return LLMResponse(text="Alpha ~80% of the window.", tool_calls=[], raw={})

    out = asyncio.run(agent_core.run_agent(ctx, reg, _Router(), max_iters=3))
    assert "80%" in out
    assert "Invoking tool" not in out


def test_run_agent_retries_promised_fetch(monkeypatch):
    from shared.agent import core as agent_core
    from shared.agent.verify import VerifyVerdict

    monkeypatch.setenv("AGENT_TRACE", "0")
    monkeypatch.setenv("AGENT_ANSWER_STREAM", "0")

    @tool(category="context")
    async def get_interval_log(ctx: AgentContext, from_ts: str = "", to_ts: str = "") -> str:
        """interval log"""
        return "value\tcount\nAlpha\t10"

    reg = ToolRegistry()
    reg.register(get_interval_log)
    ctx = AgentContext(user_id=1, domain="unified", question="август vs июль?", system_prompt="s")

    async def _select(*args, **kwargs):
        return ["get_interval_log"]

    async def _verify(text, bodies):
        return VerifyVerdict(ok=True)

    monkeypatch.setattr(agent_core, "select_tools", _select)
    monkeypatch.setattr(agent_core, "verify_draft", _verify)

    class _Router:
        async def chat_with_tools(self, messages, schemas, **kwargs):
            if not getattr(self, "n", 0):
                self.n = 1
                return LLMResponse(
                    text="Возьму всю ленту и посчитаю доли.",
                    tool_calls=[],
                    raw={},
                )
            self.n += 1
            if kwargs.get("tool_choice") == "required" or self.n == 2:
                return LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "get_interval_log",
                                "arguments": '{"from_ts":"2026-08-01","to_ts":"2026-08-19"}',
                            },
                        }
                    ],
                    raw={},
                )
            return LLMResponse(text="Alpha 10 points.", tool_calls=[], raw={})

    out = asyncio.run(agent_core.run_agent(ctx, reg, _Router(), max_iters=4))
    assert "Alpha" in out
    assert "Возьму всю ленту" not in out
