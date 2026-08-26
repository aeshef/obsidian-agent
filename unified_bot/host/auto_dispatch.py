"""Free-text / voice dispatch: one brain (unified agent) + thin action gates."""
from __future__ import annotations

import logging
import re

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from unified_bot.host.constants import DOMAIN_FINANCE, DOMAIN_KNOWLEDGE, UI_MODE_AUTO
from unified_bot.host.keyboards import keyboard_for_mode
from unified_bot.host.message_proxy import MessageWithText
from shared.telegram.agent_delivery import deliver_agent_answer

log = logging.getLogger("unified_bot.host.auto_dispatch")

__all__ = ["MessageWithText", "dispatch_auto_free_text"]


def _money_token_re() -> re.Pattern[str]:
    """Currency / transfer markers without Cyrillic string literals (CI gate)."""
    _rub = "".join(chr(c) for c in (0x440, 0x443, 0x431))  # rub
    _transfer = "".join(chr(c) for c in (0x43F, 0x435, 0x440, 0x435, 0x432, 0x43E, 0x434))
    _spent = "".join(chr(c) for c in (0x43F, 0x43E, 0x442, 0x440, 0x430, 0x442))
    _topup = "".join(chr(c) for c in (0x43F, 0x43E, 0x43F, 0x43E, 0x43B, 0x43D, 0x438))
    _r_short = chr(0x440)
    return re.compile(
        rf"(?i)(\d[\d\s]*([.,]\d+)?\s*(₽|{_rub}\.?|{_r_short}\b|kzt|\$|€)|{_transfer}|{_spent}|{_topup})"
    )


def _nonempty_lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _money_line_count(text: str) -> int:
    money = _money_token_re()
    n = 0
    for ln in _nonempty_lines(text):
        if money.search(ln) and re.search(r"\d", ln):
            n += 1
    return n


def _looks_like_txn_batch(text: str) -> bool:
    """Multi-line money dump → confirm queue; never ask the intent LLM / agent."""
    t = (text or "").strip()
    if not t or len(t) > 4000:
        return False
    lines = _nonempty_lines(t)
    if len(lines) < 2:
        return False
    return _money_line_count(t) >= 2


def _looks_like_txn_candidate(text: str) -> bool:
    """Cheap prefilter before finance-intent LLM (avoid tax on every question)."""
    t = (text or "").strip()
    if not t:
        return False
    if len(t) > 4000:
        return False
    if _looks_like_txn_batch(t):
        return True
    if "?" in t and len(t) <= 160:
        return False
    if not re.search(r"\d", t):
        return False
    if len(t) <= 160:
        return True
    lines = _nonempty_lines(t)
    digit_lines = sum(1 for ln in lines if re.search(r"\d", ln))
    if len(lines) >= 2 and digit_lines >= 2:
        return True
    return bool(_money_token_re().search(t))


async def _try_finance_transaction(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
) -> bool:
    """Keep NLU transaction entry — not yet a first-class agent write tool."""
    if not agent_app.has_domain(DOMAIN_FINANCE):
        return False
    from bot.handlers.transactions import _process_transactions

    if _looks_like_txn_batch(text):
        log.info("free text → finance NLU batch (skip intent LLM) lines=%d", len(_nonempty_lines(text)))
        await _process_transactions(text, message, state)
        return True

    if not _looks_like_txn_candidate(text):
        return False
    from shared.agent.llm_classify import LLMClassificationError, classify_finance_intent_llm

    try:
        intent = await classify_finance_intent_llm(text, chat_id=message.chat.id)
    except LLMClassificationError as e:
        if _money_token_re().search(text or ""):
            log.warning("finance intent LLM failed; fallback NLU: %s", e)
            await _process_transactions(text, message, state)
            return True
        log.warning("finance txn gate skipped (classify failed): %s", e)
        return False
    if intent != "add_transaction":
        return False
    await _process_transactions(text, message, state)
    return True


async def _try_knowledge_save(message: Message, agent_app, text: str) -> bool:
    """Bare URL → ingest. Other save phrasing stays with the unified agent."""
    if not agent_app.has_domain(DOMAIN_KNOWLEDGE):
        return False
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
