"""Reply keyboards for multi-domain host (single Telegram bot)."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from shared.i18n import msg
from shared.telegram.host import labels as L
from shared.telegram.keyboards import append_button_rows


def configure_host_keyboards() -> None:
    """Footer home button on embedded domain reply keyboards."""
    from planning_bot.app.keyboards import set_keyboard_extras

    set_keyboard_extras([[KeyboardButton(text=L.back_home())]])


def root_keyboard() -> ReplyKeyboardMarkup:
    from shared.capabilities.profile import (
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        get_capabilities,
    )

    prof = get_capabilities()
    rows: list[list[KeyboardButton]] = []
    top: list[KeyboardButton] = []
    if prof.module(MODULE_FINANCE):
        top.append(KeyboardButton(text=L.mode_finance()))
    if prof.module(MODULE_PLANNING):
        top.append(KeyboardButton(text=L.mode_planning()))
    if top:
        rows.append(top)
    bottom: list[KeyboardButton] = []
    if prof.module(MODULE_KNOWLEDGE):
        bottom.append(KeyboardButton(text=L.mode_knowledge()))
    bottom.append(KeyboardButton(text=L.mode_auto()))
    rows.append(bottom)
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder=msg("host", "placeholder_root", default="Choose mode or ask a question"),
    )


def finance_keyboard() -> ReplyKeyboardMarkup:
    from bot.handlers.start import main_menu_reply

    return append_button_rows(main_menu_reply(), [[L.back_home()]])


def planning_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.app import keyboards as pb_kb

    return pb_kb.get_main_keyboard()


def knowledge_keyboard(*, bulk_active: bool = False) -> ReplyKeyboardMarkup:
    from knowledge_bot.app.state import BTN_BULK_OFF, BTN_BULK_ON, BTN_QUERY

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BULK_OFF if bulk_active else BTN_BULK_ON)],
            [KeyboardButton(text=BTN_QUERY)],
            [KeyboardButton(text=L.back_home())],
        ],
        resize_keyboard=True,
        input_field_placeholder=msg(
            "host", "placeholder_knowledge", default="Media ingest or question about notes"
        ),
    )


def auto_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=L.back_home())]],
        resize_keyboard=True,
        input_field_placeholder=msg(
            "host", "placeholder_auto", default="Question — domain is auto-selected"
        ),
    )


def keyboard_for_mode(mode: str, user_id: int | None = None) -> ReplyKeyboardMarkup:
    from shared.capabilities.profile import (
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        get_capabilities,
    )

    prof = get_capabilities()
    if mode == "finance" and prof.module(MODULE_FINANCE):
        return finance_keyboard()
    if mode == "planning" and prof.module(MODULE_PLANNING):
        return planning_keyboard()
    if mode == "knowledge" and prof.module(MODULE_KNOWLEDGE):
        from knowledge_bot.app.state import is_bulk_ingest

        return knowledge_keyboard(bulk_active=is_bulk_ingest(user_id) if user_id else False)
    return auto_keyboard()
