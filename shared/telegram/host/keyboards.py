"""Reply keyboards for multi-domain host (single Telegram bot)."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from shared.i18n import msg
from shared.telegram.host import labels as L
from shared.telegram.keyboards import append_button_rows
from shared.telegram.push_policy import show_auto_mode_button, show_knowledge_query_button


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
    # Free text always hits the unified agent — separate Assistant button is optional.
    if show_auto_mode_button():
        bottom.append(KeyboardButton(text=L.mode_auto()))
    if bottom:
        rows.append(bottom)
    rows.append([KeyboardButton(text=L.memory_menu())])
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
    from knowledge_bot.app import kb_labels as kb_lbl
    from shared.telegram.keyboards import reply_keyboard_from_rows

    bulk_btn = kb_lbl.bulk_off() if bulk_active else kb_lbl.bulk_on()
    button_rows: list[list[str]] = [[bulk_btn]]
    # Free text already uses the unified agent — tip button is optional noise.
    if show_knowledge_query_button():
        button_rows.append([kb_lbl.query_button()])
    button_rows.append([L.back_home()])
    rows = reply_keyboard_from_rows(
        button_rows,
        resize_keyboard=True,
        input_field_placeholder=msg(
            "host", "placeholder_knowledge", default="Media ingest or question about notes"
        ),
    )
    return rows


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
    from shared.telegram.host.constants import (
        DOMAIN_FINANCE,
        DOMAIN_KNOWLEDGE,
        DOMAIN_PLANNING,
    )

    prof = get_capabilities()
    if mode == DOMAIN_FINANCE and prof.module(MODULE_FINANCE):
        return finance_keyboard()
    if mode == DOMAIN_PLANNING and prof.module(MODULE_PLANNING):
        return planning_keyboard()
    if mode == DOMAIN_KNOWLEDGE and prof.module(MODULE_KNOWLEDGE):
        from knowledge_bot.app.state import is_bulk_ingest

        return knowledge_keyboard(bulk_active=is_bulk_ingest(user_id) if user_id else False)
    return auto_keyboard()
