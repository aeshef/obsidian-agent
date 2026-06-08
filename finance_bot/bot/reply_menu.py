"""Finance reply-menu: dispatch from ui_capabilities menu_actions + handler registry."""
from __future__ import annotations

from typing import Awaitable, Callable

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config_loader import get_badge_config, get_nlu_config, is_badge_enabled, nlu_menu_buttons
from bot.menu_labels import finance_menu_aliases, finance_menu_texts, fin_menu
from shared.capabilities.menu_actions_config import menu_reply_specs
from shared.telegram.reply_menu_dispatch import dispatch_by_label_map

Handler = Callable[[Message, FSMContext], Awaitable[None]]

_handler_map: dict[str, Handler] | None = None


def _finance_handler_registry() -> dict[str, Handler]:
    from bot.handlers import start as h

    return {
        "balance": h.handle_balance_button,
        "last_ops": h.handle_last_button,
        "badge": h.handle_badge_button,
    }


def _build_handler_map() -> dict[str, Handler]:
    from shared.capabilities.ui_bindings import message_allowed as allowed

    t = finance_menu_texts()
    registry = _finance_handler_registry()
    canonical: dict[str, Handler] = {}

    for spec in menu_reply_specs("finance"):
        menu_key = str(spec.get("menu_key") or "").strip()
        action_id = str(spec.get("action") or "").strip()
        if not menu_key or not action_id:
            continue
        if not allowed("finance", "menu", menu_key):
            continue
        if spec.get("requires_badge") and not is_badge_enabled():
            continue
        handler = registry.get(action_id)
        if handler is None:
            continue
        if menu_key == "badge":
            label = (get_badge_config().get("ui") or {}).get("menu_button") or fin_menu("badge")
        else:
            label = t.get(menu_key) or fin_menu(menu_key)
        if label:
            canonical[label] = handler

    cfg = get_nlu_config()
    configured = nlu_menu_buttons(cfg)
    if configured:
        missing = configured - set(canonical)
        if missing:
            raise RuntimeError(f"nlu menu_buttons without handlers: {sorted(missing)}")

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
