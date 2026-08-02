"""FinanceAdapter.try_fast_answer uses routing.yaml patterns."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.agent.types import AgentContext


@pytest.mark.asyncio
async def test_balance_fast_path(tmp_path: Path, monkeypatch):
    agent = tmp_path / "config" / "agent"
    agent.mkdir(parents=True)
    (agent / "routing.yaml").write_text(
        "host:\n"
        "  fast_answer:\n"
        "    finance_balance:\n"
        "      - '\\bbalance\\b'\n"
        "      - '\\bбаланс\\b'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    from shared.agent import config as acfg

    acfg.load_routing_config.cache_clear()

    # Prefer the same import path the runtime registry uses (finance_bot on sys.path → bot.*).
    import bot.agent_tools as fat

    clear = getattr(fat._finance_balance_fast_re, "cache_clear", None)
    if callable(clear):
        clear()

    adapter = fat.FinanceAdapter(analyst=MagicMock())
    monkeypatch.setattr(
        fat,
        "get_balance",
        AsyncMock(return_value="Account balances:\nCash: 100"),
    )
    ctx = AgentContext(user_id=1, domain="finance", question="balance", system_prompt="")
    ans = await adapter.try_fast_answer(ctx)
    assert ans is not None
    assert "100" in ans.text

    ctx2 = AgentContext(
        user_id=1,
        domain="finance",
        question="compare food spend with tasks last month",
        system_prompt="",
    )
    assert await adapter.try_fast_answer(ctx2) is None
