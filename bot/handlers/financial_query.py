"""
Financial query handler — LLM router (finance_query | add_transaction | chitchat).

Transactions via NLU; Q&A via AgentApp or FinancialAnalyst.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state

from bot.ui import fmsg
from shared.agent.llm_classify import LLMClassificationError, classify_finance_intent_llm
from shared.agent.routing import deploy_mode
from shared.telegram.agent_delivery import deliver_agent_answer
from shared.telegram.navigation import is_host_navigation
from shared.telegram.limits import max_message_chars
from shared.telegram.messaging import send_long_message
from shared.telegram_utils import strip_telegram_markdown

from ..config_loader import get_nlu_config, nlu_exact_commands, nlu_menu_buttons
from ..services.financial_analyst import FinancialAnalyst

if TYPE_CHECKING:
    from shared.agent.app import AgentApp

log = logging.getLogger("finance.query")

router = Router()


async def handle_smart_text(
    message: types.Message,
    state: FSMContext,
    *,
    agent_app: Optional["AgentApp"] = None,
    text_override: str | None = None,
) -> None:
    text = (text_override or message.text or "").strip()

    if not text:
        return

    if text.startswith("/"):
        return

    nlu_cfg = get_nlu_config()
    if is_host_navigation(text):
        return

    if text in nlu_exact_commands(nlu_cfg) or text in nlu_menu_buttons(nlu_cfg):
        return

    chat_id = message.chat.id
    try:
        intent = await classify_finance_intent_llm(text, chat_id=chat_id)
    except LLMClassificationError as e:
        log.error("finance intent LLM failed: %s", e, exc_info=True)
        await message.answer(fmsg("finance_llm_unavailable", error=e))
        return
    log.info("Router: intent='%s' for text='%.60s'", intent, text)

    if intent == "add_transaction":
        from .transactions import _process_transactions

        await _process_transactions(text, message, state)
        return

    if agent_app is not None and agent_app.has_domain("finance"):
        try:
            await deliver_agent_answer(
                message.bot,
                chat_id,
                agent_app,
                text,
                domain="finance",
            )
        except Exception as e:
            log.error("agent_app finance answer failed: %s", e, exc_info=True)
            await message.answer(fmsg("finance_no_answer"))
        return

    if deploy_mode() == "single":
        log.error("finance query without AgentApp in single-bot mode")
        await message.answer(fmsg("finance_agent_missing"))
        return

    thinking = await message.answer(fmsg("finance_thinking"))
    try:
        answer = await FinancialAnalyst().answer_query(message.from_user.id, text)
        plain = strip_telegram_markdown(answer)[: max_message_chars()]
        await thinking.edit_text(plain)
    except Exception as e:
        log.error("answer_query failed: %s", e, exc_info=True)
        await thinking.edit_text(fmsg("finance_data_no_answer"))


@router.message(StateFilter(default_state), F.text)
async def handle_smart_text_route(message: types.Message, state: FSMContext) -> None:
    await handle_smart_text(message, state, agent_app=None)
