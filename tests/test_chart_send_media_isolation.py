"""Chart sends must not mix with knowledge-note media."""
from __future__ import annotations

from shared.agent.chart_tools import rank_charts_for_query, score_chart_match
from shared.agent.media_queue import (
    collect_outbound_media,
    queue_chart_media,
    queue_vault_media,
)
from shared.agent.types import AgentContext, CHART_MEDIA_EXTRAS_KEY, KB_MEDIA_EXTRAS_KEY
from shared.charts_catalog import ChartEntry


def _ctx() -> AgentContext:
    return AgentContext(
        user_id=1,
        domain="unified",
        question="x",
        system_prompt="",
        extras={},
    )


def test_charts_win_over_kb_media():
    ctx = _ctx()
    queue_vault_media(ctx, [("notes/a.png", "kb")], max_total=6)
    queue_chart_media(ctx, [("charts/cost.png", "cost")], max_total=4)
    out = collect_outbound_media(ctx)
    assert out == [("charts/cost.png", "cost")]
    assert len(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or []) == 1
    assert len(ctx.extras.get(CHART_MEDIA_EXTRAS_KEY) or []) == 1


def test_kb_media_alone_still_delivered():
    ctx = _ctx()
    queue_vault_media(ctx, [("notes/a.png", "kb")], max_total=6)
    assert collect_outbound_media(ctx) == [("notes/a.png", "kb")]


def test_rank_tie_breaks_newer_mtime():
    old = ChartEntry(
        key="chart_finance_a_png",
        rel_path="Charts/Finance/a.png",
        family="finance",
        exists=True,
        mtime_iso="2026-06-08T00:00:00+00:00",
    )
    new = ChartEntry(
        key="chart_finance_b_png",
        rel_path="Charts/Finance/b.png",
        family="finance",
        exists=True,
        mtime_iso="2026-08-18T00:00:00+00:00",
    )
    ranked = rank_charts_for_query([old, new], "finance")
    assert ranked[0].key == "chart_finance_b_png"


def test_prefer_fresh_same_family_over_stale_named(monkeypatch):
    from shared.agent import chart_tools as ct

    monkeypatch.setattr(ct, "_stale_hours", lambda: 48)
    stale = ChartEntry(
        key="chart_finance_spend_png",
        rel_path="Charts/Finance/Spending_by_day_category.png",
        family="finance",
        exists=True,
        mtime_iso="2026-06-08T00:00:00+00:00",
    )
    fresh = ChartEntry(
        key="chart_finance_balance_png",
        rel_path="Charts/Finance/Balance.png",
        family="finance",
        exists=True,
        mtime_iso="2026-08-18T00:00:00+00:00",
    )
    other = ChartEntry(
        key="chart_planning_activity_png",
        rel_path="Charts/Planning/Daily_activity.png",
        family="planning",
        exists=True,
        mtime_iso="2026-08-18T00:00:00+00:00",
    )
    out = ct._prefer_fresh([stale, other, fresh], stale_h=48)
    assert out[0].key == "chart_finance_balance_png"
    assert other in out


def test_score_prefers_cost_chart():
    cost = ChartEntry(
        key="chart_agent_cost_daily_png",
        rel_path="300/Графики/Система/Агент_стоимость_день.png",
        family="analytics",
        exists=True,
    )
    tokens = ChartEntry(
        key="chart_agent_tokens_daily_png",
        rel_path="300/Графики/Система/Агент_токены_день.png",
        family="analytics",
        exists=True,
    )
    tools = ChartEntry(
        key="chart_agent_tools_png",
        rel_path="300/Графики/Система/Агент_тулы.png",
        family="analytics",
        exists=True,
    )
    q = "график стоимости агента"
    assert score_chart_match(cost, q) > score_chart_match(tokens, q)
    assert score_chart_match(cost, q) > score_chart_match(tools, q)
    ranked = rank_charts_for_query([tokens, tools, cost], q)
    assert ranked[0].key == "chart_agent_cost_daily_png"


def test_send_generic_query_does_not_collapse_to_one(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    from shared.vault_paths_config import vault_paths_config
    from shared.chart_paths import charts_root
    from shared.agent.chart_tools import send_vault_charts
    from shared.agent.types import AgentContext, CHART_MEDIA_EXTRAS_KEY

    vault_paths_config.cache_clear()
    root = charts_root(tmp_path)
    for name in ("a.png", "b.png"):
        png = root / "Finance" / name
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"\x89PNG\r\n\x1a\n")

    ctx = AgentContext(
        user_id=1,
        domain="unified",
        question="скинь графики самые крутые",
        system_prompt="",
        extras={},
    )
    out = asyncio.run(send_vault_charts(ctx, query="", limit=0))
    media = ctx.extras.get(CHART_MEDIA_EXTRAS_KEY) or []
    assert len(media) >= 2, out


def test_send_with_bot_delivers_immediately(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    from shared.vault_paths_config import vault_paths_config
    from shared.chart_paths import charts_root
    from shared.agent.chart_tools import send_vault_charts
    from shared.agent.types import AgentContext, CHART_MEDIA_EXTRAS_KEY

    vault_paths_config.cache_clear()
    root = charts_root(tmp_path)
    png = root / "Health" / "trends.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    bot = MagicMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()
    ctx = AgentContext(
        user_id=1,
        domain="unified",
        question="trends",
        system_prompt="",
        extras={"telegram_bot": bot, "telegram_id": 7},
    )
    out = asyncio.run(send_vault_charts(ctx, query="trends", limit=1))
    assert bot.send_photo.await_count == 1, out
    assert not (ctx.extras.get(CHART_MEDIA_EXTRAS_KEY) or [])
