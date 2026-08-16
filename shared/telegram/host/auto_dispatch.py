"""Free-text / voice dispatch: one brain (unified agent) + thin action gates."""
from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.telegram.host.auto_routing import MessageWithText, auto_handler_for
from shared.telegram.host.constants import UI_MODE_AUTO
from shared.telegram.host.keyboards import keyboard_for_mode
from shared.telegram.agent_delivery import deliver_agent_answer

log = logging.getLogger("shared.telegram.host.auto_dispatch")

# Re-export for callers that build ASR proxies.
__all__ = ["MessageWithText", "dispatch_auto_free_text", "auto_handler_for"]


def _looks_like_txn_candidate(text: str) -> bool:
    """Cheap prefilter before finance-intent LLM (avoid tax on every question).

    Short money notes and multi-line dumps (confirm queue) both qualify.
    Hard length was 160 and silently dropped bulk transfer lists into unified chat.
    """
    import re

    t = (text or "").strip()
    if not t or "?" in t:
        return False
    if not re.search(r"\d", t):
        return False
    # Telegram message ceiling; NLU handles batch lists.
    if len(t) > 4000:
        return False
    if len(t) <= 160:
        return True
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    digit_lines = sum(1 for ln in lines if re.search(r"\d", ln))
    if len(lines) >= 2 and digit_lines >= 2:
        return True
    # Single long line still ok if it looks money-like (voice ASR blobs, etc.)
    # Currency words built from codepoints (no Cyrillic literals — CI gate).
    _rub = "".join(chr(c) for c in (0x440, 0x443, 0x431))  # rub
    _transfer = "".join(chr(c) for c in (0x43F, 0x435, 0x440, 0x435, 0x432, 0x43E, 0x434))
    _spent = "".join(chr(c) for c in (0x43F, 0x43E, 0x442, 0x440, 0x430, 0x442))
    _topup = "".join(chr(c) for c in (0x43F, 0x43E, 0x43F, 0x43E, 0x43B, 0x43D, 0x438))
    _r_short = chr(0x440)
    return bool(
        re.search(
            rf"(?i)(\d[\d\s]*([.,]\d+)?\s*(₽|{_rub}\.?|{_r_short}\b|kzt|\$|€)|{_transfer}|{_spent}|{_topup})",
            t,
        )
    )


async def _try_finance_transaction(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
) -> bool:
    """Keep NLU transaction entry — not yet a first-class agent write tool."""
    if not agent_app.has_domain("finance"):
        return False
    if not _looks_like_txn_candidate(text):
        return False
    from shared.agent.llm_classify import LLMClassificationError, classify_finance_intent_llm

    try:
        intent = await classify_finance_intent_llm(text, chat_id=message.chat.id)
    except LLMClassificationError as e:
        log.warning("finance txn gate skipped (classify failed): %s", e)
        return False
    if intent != "add_transaction":
        return False
    from bot.handlers.transactions import _process_transactions

    await _process_transactions(text, message, state)
    return True


async def _try_knowledge_save(message: Message, agent_app, text: str) -> bool:
    """Bare URL → ingest. Other save phrasing stays with the unified agent."""
    if not agent_app.has_domain("knowledge"):
        return False
    import re

    if not re.match(r"^https?://\S+$", (text or "").strip(), re.IGNORECASE):
        return False
    from knowledge_bot.app.handlers.query import handle_message as kb_handle

    await kb_handle(MessageWithText(message, text))
    return True


async def dispatch_auto_free_text(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
) -> None:
    """Pinned or Auto: free text → unified agent (all tools), with action gates.

    Menu buttons are handled earlier by domain_dispatch. Here we only keep
    thin host actions that are not agent tools yet (txn NLU, knowledge save),
    then answer with the full unified harness.
    """
    data = await state.get_data()
    uid = message.from_user.id if message.from_user else message.chat.id
    ui_mode = data.get("ui_mode", UI_MODE_AUTO)

    try:
        from knowledge_bot.app.state import is_bulk_ingest

        if is_bulk_ingest(uid):
            from knowledge_bot.app.handlers.query import handle_message as kb_handle

            await kb_handle(MessageWithText(message, text))
            return
    except Exception:
        pass

    if await _try_finance_transaction(message, state, agent_app, text):
        log.info("free text → finance transaction len=%d", len(text))
        return

    if await _try_knowledge_save(message, agent_app, text):
        log.info("free text → knowledge save len=%d", len(text))
        return

    log.info("free text → unified ui_mode=%s len=%d", ui_mode, len(text))
    await deliver_agent_answer(
        message.bot,
        message.chat.id,
        agent_app,
        text,
        unified=True,
        reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
    )
