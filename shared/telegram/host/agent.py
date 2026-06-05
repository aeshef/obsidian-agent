"""Host agent composition and routing (LLM-only domain pick)."""
from __future__ import annotations

import logging

from shared.agent.app import AgentApp, build_app
from shared.agent.llm_classify import (
    LLMClassificationError,
    classify_host_domain_llm,
)
from shared.llm import LLMClient
from shared.telegram.host.constants import DOMAIN_GENERAL, DOMAIN_IDS, DOMAIN_UNIFIED

log = logging.getLogger("shared.telegram.host.agent")

_host_planning_bot: object | None = None


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
    if fixed and agent_app.has_domain(fixed):
        return fixed
    if ui_mode in DOMAIN_IDS and agent_app.has_domain(ui_mode):
        return ui_mode

    enabled = [d for d in ("finance", "planning", "knowledge") if agent_app.has_domain(d)]
    if not enabled:
        raise RuntimeError("pick_host_domain: no domain adapters registered")

    dom_name = await classify_host_domain_llm(
        text,
        enabled=enabled,
        chat_id=chat_id,
        ui_mode=ui_mode,
    )

    if dom_name == "general":
        return DOMAIN_GENERAL
    if dom_name == "unified":
        if len(enabled) < 2:
            raise LLMClassificationError("host_domain unified but fewer than 2 adapters enabled")
        return DOMAIN_UNIFIED

    if not agent_app.has_domain(dom_name):
        raise LLMClassificationError(
            f"pick_host_domain: domain {dom_name!r} not registered (available: {agent_app.domains()})"
        )
    return dom_name
