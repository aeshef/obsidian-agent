"""Knowledge reply-keyboard dispatch (ui_capabilities menu_actions + handler registry)."""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from knowledge_bot.app import kb_labels as kb_lbl
from shared.agent.app import AgentApp
from shared.capabilities.menu_actions_config import menu_reply_specs
from shared.capabilities.ui_bindings import message_allowed
from shared.i18n import msg
from shared.telegram.reply_menu_dispatch import dispatch_by_label_map

_KB_LABEL_FN = {
    "bulk_on": kb_lbl.bulk_on,
    "bulk_off": kb_lbl.bulk_off,
    "query": kb_lbl.query_button,
    "query_legacy": kb_lbl.query_legacy,
}


def knowledge_menu_labels() -> frozenset[str]:
    labels: set[str] = set()
    for spec in menu_reply_specs("knowledge"):
        button_key = str(spec.get("button_key") or "").strip()
        if not button_key or not message_allowed("knowledge", "buttons", button_key):
            continue
        label_fn = _KB_LABEL_FN.get(button_key)
        if label_fn is None:
            continue
        label = label_fn()
        if label:
            labels.add(label)
    return frozenset(labels)


def is_knowledge_menu_button(text: str) -> bool:
    t = (text or "").strip()
    return bool(t and t in knowledge_menu_labels())


def _build_handlers(
    message: Message,
    *,
    state: Optional[FSMContext],
    reply_markup,
) -> dict[str, Callable[[], Awaitable[None]]]:
    from knowledge_bot.app.handlers.modes import disable_bulk_ingest, enable_bulk_ingest
    from knowledge_bot.app.state import is_bulk_ingest, main_reply_keyboard

    uid = message.from_user.id if message.from_user else 0
    handlers: dict[str, Callable[[], Awaitable[None]]] = {}

    for spec in menu_reply_specs("knowledge"):
        button_key = str(spec.get("button_key") or "").strip()
        action_id = str(spec.get("action") or "").strip()
        if not button_key or not message_allowed("knowledge", "buttons", button_key):
            continue
        label_fn = _KB_LABEL_FN.get(button_key)
        if label_fn is None:
            continue
        label = label_fn()
        if not label:
            continue

        if action_id == "bulk_on":

            async def _bulk_on(_m=message, _st=state):
                await enable_bulk_ingest(_m, state=_st)

            handlers[label] = _bulk_on
        elif action_id == "bulk_off":

            async def _bulk_off(_m=message, _st=state):
                await disable_bulk_ingest(_m, state=_st)

            handlers[label] = _bulk_off
        elif action_id == "query":

            async def _query(_m=message, _kb=reply_markup, _st=state, _uid=uid):
                if _st is not None:
                    await _st.update_data(kb_query_pending=True)
                kb = _kb or main_reply_keyboard(bulk_active=is_bulk_ingest(_uid))
                await _m.answer(msg("knowledge", "query_prompt"), reply_markup=kb)

            handlers[label] = _query

    return handlers


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
    return await dispatch_by_label_map(
        text,
        _build_handlers(message, state=state, reply_markup=reply_markup),
    )
