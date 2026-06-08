"""Knowledge reply-keyboard dispatch (labels from msg / ui_capabilities)."""
from __future__ import annotations

from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from knowledge_bot.app import kb_labels as kb_lbl
from shared.agent.app import AgentApp
from shared.capabilities.ui_bindings import message_allowed
from shared.i18n import msg


def knowledge_menu_labels() -> frozenset[str]:
    labels: set[str] = set()
    for cap_key in ("bulk_on", "bulk_off", "query", "query_legacy"):
        if not message_allowed("knowledge", "buttons", cap_key):
            continue
        label = kb_lbl.kb_button(cap_key)
        if label:
            labels.add(label)
    return frozenset(labels)


def is_knowledge_menu_button(text: str) -> bool:
    t = (text or "").strip()
    return bool(t and t in knowledge_menu_labels())


async def dispatch_knowledge_menu_button(
    message: Message,
    agent_app: Optional[AgentApp] = None,
    *,
    state: Optional[FSMContext] = None,
    reply_markup=None,
) -> bool:
    """Handle knowledge reply-keyboard taps. True = consumed."""
    del agent_app
    text = (message.text or "").strip()
    if not text:
        return False

    from knowledge_bot.app.handlers.modes import disable_bulk_ingest, enable_bulk_ingest
    from knowledge_bot.app.state import is_bulk_ingest, main_reply_keyboard
    from shared.telegram.host.keyboards import knowledge_keyboard

    uid = message.from_user.id if message.from_user else 0

    if message_allowed("knowledge", "buttons", "bulk_on") and text == kb_lbl.bulk_on():
        kb = reply_markup or knowledge_keyboard(bulk_active=True)
        await enable_bulk_ingest(message, reply_markup=kb, state=state)
        return True

    if message_allowed("knowledge", "buttons", "bulk_off") and text == kb_lbl.bulk_off():
        kb = reply_markup or knowledge_keyboard(bulk_active=False)
        await disable_bulk_ingest(message, reply_markup=kb, state=state)
        return True

    query_labels = []
    if message_allowed("knowledge", "buttons", "query"):
        query_labels.append(kb_lbl.query_button())
    if message_allowed("knowledge", "buttons", "query_legacy"):
        query_labels.append(kb_lbl.query_legacy())
    if text in query_labels:
        if state is not None:
            await state.update_data(kb_query_pending=True)
        kb = reply_markup or main_reply_keyboard(bulk_active=is_bulk_ingest(uid))
        await message.answer(msg("knowledge", "query_prompt"), reply_markup=kb)
        return True

    return False
