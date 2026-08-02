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


def test_score_prefers_cost_chart():
    cost = ChartEntry(
        key="chart_agent_cost_daily_png",
        rel_path="300/Графики/Аналитика/Агент_стоимость_день.png",
        family="analytics",
        exists=True,
    )
    tokens = ChartEntry(
        key="chart_agent_tokens_daily_png",
        rel_path="300/Графики/Аналитика/Агент_токены_день.png",
        family="analytics",
        exists=True,
    )
    tools = ChartEntry(
        key="chart_agent_tools_png",
        rel_path="300/Графики/Аналитика/Агент_тулы.png",
        family="analytics",
        exists=True,
    )
    q = "график стоимости агента"
    assert score_chart_match(cost, q) > score_chart_match(tokens, q)
    assert score_chart_match(cost, q) > score_chart_match(tools, q)
    ranked = rank_charts_for_query([tokens, tools, cost], q)
    assert ranked[0].key == "chart_agent_cost_daily_png"
