"""Host agent composition and routing (LLM-only domain pick)."""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from shared.agent.app import AgentApp, build_app
from shared.agent.config import load_routing_config
from shared.agent.llm_classify import (
    LLMClassificationError,
    classify_host_domain_llm,
)
from shared.llm import LLMClient
from shared.telegram.host.constants import DOMAIN_GENERAL, DOMAIN_IDS, DOMAIN_UNIFIED

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


async def pick_host_domain(
    text: str,
    ui_mode: str,
    fixed: str | None,
    agent_app: AgentApp,
    *,
    chat_id: int | None = None,
) -> str:
    """Legacy domain classifier (tests / eval). Live free text uses ``answer_unified``."""
    enabled = [d for d in ("finance", "planning", "knowledge") if agent_app.has_domain(d)]
    if not enabled:
        raise RuntimeError("pick_host_domain: no domain adapters registered")

    prefer: str | None = None
    if fixed and agent_app.has_domain(fixed):
        prefer = fixed
    elif ui_mode in DOMAIN_IDS and agent_app.has_domain(ui_mode):
        prefer = ui_mode

    # Single-domain install: pin/UI mode is decisive.
    if prefer and len(enabled) < 2:
        return prefer

    # Cheap heuristic for unambiguous single-domain phrases (skip LLM).
    from shared.agent.cheap_router import cheap_route_domain

    cheap = cheap_route_domain(
        text,
        enabled=enabled,
        cross_domain_check=_looks_finance_planning_cross,
    )
    if cheap and agent_app.has_domain(cheap) and (not prefer or prefer == cheap):
        return cheap

    # Multi-domain: classify. A pinned UI mode is a hint (passed as ui_mode),
    # but "unified" must escape the pin — otherwise food×tasks stuck in finance-only.
    hint = prefer or ui_mode
    dom_name = await classify_host_domain_llm(
        text,
        enabled=enabled,
        chat_id=chat_id,
        ui_mode=hint,
    )

    if dom_name == "general":
        return DOMAIN_GENERAL
    if dom_name == "unified":
        return DOMAIN_UNIFIED

    # Router sometimes under-selects a single domain for join questions — escalate.
    if (
        dom_name in ("finance", "planning")
        and "finance" in enabled
        and "planning" in enabled
        and _looks_finance_planning_cross(text)
    ):
        log.info(
            "host domain escalate %s -> unified (cross finance+planning) text=%.50s",
            dom_name,
            text,
        )
        return DOMAIN_UNIFIED

    if prefer and dom_name != prefer:
        # Stay in the pinned single domain unless escalated to unified above.
        return prefer

    if not agent_app.has_domain(dom_name):
        raise LLMClassificationError(
            f"pick_host_domain: domain {dom_name!r} not registered (available: {agent_app.domains()})"
        )
    return dom_name
