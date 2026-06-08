"""Finance reply-menu: dispatch main-menu reply buttons (host + standalone router)."""
from __future__ import annotations

from typing import Awaitable, Callable

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config_loader import get_badge_config, get_nlu_config, is_badge_enabled, nlu_menu_buttons
from bot.menu_labels import finance_menu_aliases, finance_menu_texts, fin_menu
from shared.telegram.reply_menu_dispatch import dispatch_by_label_map

Handler = Callable[[Message, FSMContext], Awaitable[None]]

_handler_map: dict[str, Handler] | None = None


def _build_handler_map() -> dict[str, Handler]:
    from bot.handlers import start as h
    from shared.capabilities.ui_bindings import message_allowed

    t = finance_menu_texts()
    # Reply keyboard only for kept actions; wizard labels route via agent/NLU.
    canonical: dict[str, Handler] = {}
    if message_allowed("finance", "menu", "balance"):
        canonical[t["balance"]] = h.handle_balance_button
    if message_allowed("finance", "menu", "last_ops"):
        canonical[t["last_ops"]] = h.handle_last_button
    cfg = get_nlu_config()
    configured = nlu_menu_buttons(cfg)
    if configured:
        missing = configured - set(canonical)
        if missing:
            raise RuntimeError(f"nlu menu_buttons without handlers: {sorted(missing)}")

    if is_badge_enabled() and message_allowed("finance", "menu", "badge"):
        badge = (get_badge_config().get("ui") or {}).get("menu_button") or fin_menu("badge")
        if badge:
            canonical[badge] = h.handle_badge_button

    out = dict(canonical)
    for alias, label in finance_menu_aliases().items():
        if label in canonical:
            out[alias] = canonical[label]
    return out


def reply_menu_handlers() -> dict[str, Handler]:
    global _handler_map
    if _handler_map is None:
        _handler_map = _build_handler_map()
    return _handler_map


def normalize_reply_label(text: str) -> str:
    t = text.strip()
    return finance_menu_aliases().get(t, t)


def is_reply_menu_button(text: str) -> bool:
    return normalize_reply_label(text.strip()) in reply_menu_handlers()


async def dispatch_reply_menu_button(message: Message, state: FSMContext) -> bool:
    return await dispatch_by_label_map(
        message.text or "",
        reply_menu_handlers(),
        message,
        state,
        normalize=normalize_reply_label,
    )
