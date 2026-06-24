"""Context collection for Memory Synthesizer (domain aggregates, no LLM)."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from shared.agent.platform_config import platform_int
from shared.i18n import msg, msgf
from shared.memory.session import get_history

log = logging.getLogger("shared.memory.context")

ContextCollector = Callable[[int], Awaitable[str]]


def _dialogue_excerpt(user_id: int, domain: str) -> str:
    hist = get_history(user_id, domain)
    if not hist:
        return ""
    excerpt_chars = platform_int("memory_synth", "dialogue_excerpt_chars", default=200)
    history_turns = platform_int("memory_synth", "dialogue_history_turns", default=6)
    lines = [
        f"{m.role} [{m.ts or 'time_unknown'}]: {(m.content or '')[:excerpt_chars]}"
        for m in hist[-history_turns:]
    ]
    return msgf("memory_context", "recent_dialogue", lines="\n".join(lines))


async def collect_finance_context(user_id: int) -> str:
    from shared.agent.types import AgentContext

    try:
        from bot.agent_tools import compute_summary, get_balance, get_recent
    except ImportError:
        from finance_bot.bot.agent_tools import compute_summary, get_balance, get_recent

    ctx = AgentContext(
        user_id=user_id,
        domain="finance",
        question="synth",
        system_prompt="",
        extras={"telegram_id": user_id},
    )
    try:
        try:
            from bot.services.financial_analyst import FinancialAnalyst
        except ImportError:
            from finance_bot.bot.services.financial_analyst import FinancialAnalyst

        ctx.extras["analyst"] = FinancialAnalyst()
    except Exception as e:
        log.warning("finance analyst for synth: %s", e)

    days = platform_int("memory_synth", "finance_context_days", default=28)
    recent_n = platform_int("memory_synth", "finance_recent_transactions", default=15)
    parts = [
        msgf("memory_context", "finance_header", days=days),
        await get_balance(ctx),
        await compute_summary(ctx),
        await get_recent(ctx, n=recent_n),
    ]
    excerpt = _dialogue_excerpt(user_id, "finance")
    if excerpt:
        parts.append(excerpt)
    return "\n\n".join(parts)


async def collect_planning_context(user_id: int) -> str:
    """Planning snapshot (log, goals, kanban) + recent dialogue from shared session."""
    try:
        from shared.telegram.host.agent import get_host_planning_bot

        bot = get_host_planning_bot()
        if bot is None:
            from planning_bot.app.bot import PlanningBot

            bot = PlanningBot()
        from planning_bot.services.planning_snapshot import assemble_planning_snapshot

        snapshot = assemble_planning_snapshot(
            kanban=bot.kanban,
            goals_manager=bot.goals_manager,
            action_logger=bot.logger,
        )
        parts = [msg("memory_context", "planning_header"), snapshot]
        excerpt = _dialogue_excerpt(user_id, "planning")
        if excerpt:
            parts.append(excerpt)
        return "\n\n".join(parts)
    except Exception as e:
        log.warning("planning context collect failed: %s", e)
        return ""


async def collect_knowledge_context(user_id: int) -> str:
    try:
        from knowledge_bot.core.config import load_config
        from knowledge_bot.services.indexer import load_index

        cfg = load_config()
        idx = load_index()
        n = len(idx.get("entries") or [])
        parts = [
            msgf(
                "memory_context",
                "knowledge_header",
                count=n,
                vault_name=cfg.vault_path.name,
            )
        ]
        excerpt = _dialogue_excerpt(user_id, "knowledge")
        if excerpt:
            parts.append(excerpt)
        return "\n".join(parts)
    except Exception as e:
        log.warning("knowledge context collect failed: %s", e)
        return ""


COLLECTORS: dict[str, ContextCollector] = {
    "finance": collect_finance_context,
    "planning": collect_planning_context,
    "knowledge": collect_knowledge_context,
}
