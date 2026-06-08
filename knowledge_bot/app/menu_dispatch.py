"""Knowledge reply-keyboard dispatch (labels from msg / ui_capabilities)."""
from __future__ import annotations

from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from knowledge_bot.app import kb_labels as kb_lbl
from shared.agent.app import AgentApp
from shared.capabilities.ui_bindings import message_allowed
from shared.i18n import msg
from shared.telegram.reply_menu_dispatch import dispatch_by_label_map


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
    handlers: dict[str, object] = {}

    if message_allowed("knowledge", "buttons", "bulk_on"):
        label = kb_lbl.bulk_on()
        if label:

            async def _bulk_on(_m=message, _kb=reply_markup, _st=state):
                kb = _kb or knowledge_keyboard(bulk_active=True)
                await enable_bulk_ingest(_m, reply_markup=kb, state=_st)

            handlers[label] = _bulk_on

    if message_allowed("knowledge", "buttons", "bulk_off"):
        label = kb_lbl.bulk_off()
        if label:

            async def _bulk_off(_m=message, _kb=reply_markup, _st=state):
                kb = _kb or knowledge_keyboard(bulk_active=False)
                await disable_bulk_ingest(_m, reply_markup=kb, state=_st)

            handlers[label] = _bulk_off

    for cap_key, label_fn in (("query", kb_lbl.query_button), ("query_legacy", kb_lbl.query_legacy)):
        if not message_allowed("knowledge", "buttons", cap_key):
            continue
        label = label_fn()
        if not label:
            continue

        async def _query(_m=message, _kb=reply_markup, _st=state, _uid=uid):
            if _st is not None:
                await _st.update_data(kb_query_pending=True)
            kb = _kb or main_reply_keyboard(bulk_active=is_bulk_ingest(_uid))
            await _m.answer(msg("knowledge", "query_prompt"), reply_markup=kb)

        handlers[label] = _query

    return await dispatch_by_label_map(text, handlers)
