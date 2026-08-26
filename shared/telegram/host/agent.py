"""Host agent composition (unified free text — no legacy domain picker)."""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from shared.agent.app import AgentApp, build_app
from shared.agent.config import load_routing_config
from shared.llm import LLMClient

log = logging.getLogger("shared.telegram.host.agent")

_host_planning_bot: object | None = None

# English-only fallbacks when routing.yaml omits cross_domain_escalation patterns.
_DEFAULT_FINANCE_PATTERN = r"(finance|spend|food|budget|balance|expense)"
_DEFAULT_PLANNING_PATTERN = r"(task|kanban|completion|health|sleep|calendar|productivity)"


@lru_cache(maxsize=1)
def _cross_domain_patterns() -> tuple[re.Pattern[str], re.Pattern[str]]:
    host = load_routing_config().get("host") or {}
    esc = host.get("cross_domain_escalation") or {}
    finance = str(esc.get("finance_pattern") or "").strip() or _DEFAULT_FINANCE_PATTERN
    planning = str(esc.get("planning_pattern") or "").strip() or _DEFAULT_PLANNING_PATTERN
    return (
        re.compile(finance, re.IGNORECASE),
        re.compile(planning, re.IGNORECASE),
    )


def _looks_finance_planning_cross(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    money_re, planning_re = _cross_domain_patterns()
    return bool(money_re.search(t) and planning_re.search(t))


def get_host_planning_bot():
    """Unified PlanningBot host (bootstrap + memory collectors)."""
    return _host_planning_bot


def build_host_agent_app(planning_bot=None) -> AgentApp:
    global _host_planning_bot
    from shared.capabilities.profile import (
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        get_capabilities,
    )

    llm = LLMClient()
    prof = get_capabilities()
    adapters = []
    if prof.module(MODULE_FINANCE):
        try:
            from bot.agent_tools import FinanceAdapter
            from bot.services.financial_analyst import FinancialAnalyst

            adapters.append(FinanceAdapter(FinancialAnalyst()))
        except Exception as e:
            log.warning("finance adapter unavailable: %s", e)
    if prof.module(MODULE_PLANNING):
        try:
            from planning_bot.app.agent_tools import PlanningAdapter
            from planning_bot.app.bot import PlanningBot

            pb = planning_bot if planning_bot is not None else PlanningBot()
            _host_planning_bot = pb
            adapters.append(PlanningAdapter(pb))
        except Exception as e:
            log.error(
                "planning module enabled but adapter failed (auto-routing will not offer planning): %s",
                e,
                exc_info=True,
            )
    if prof.module(MODULE_KNOWLEDGE):
        try:
            from knowledge_bot.app.agent_tools import KnowledgeAdapter

            adapters.append(KnowledgeAdapter())
        except Exception as e:
            log.warning("knowledge adapter unavailable: %s", e)
    if not adapters:
        raise RuntimeError("no domain adapters loaded (check config/agent/capabilities.yaml)")
    log.info("host adapters enabled: %s", [a.domain for a in adapters])
    return build_app(llm, *adapters)
