"""Planning reply keyboards (config/messages.{locale}.yaml)."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from planning_bot.app.ui import pmsg_menu


class ReplyKeyboardExtras:
    """Optional footer rows appended by a host process (e.g. unified bot).

    Standalone bots leave extras empty; a host calls ``set()`` once at startup.
    Domain keyboard builders call ``apply()`` before returning markup.
    """

    def __init__(self) -> None:
        self._rows: list[list[KeyboardButton]] = []

    def set(self, rows: list[list[KeyboardButton]] | None) -> None:
        self._rows = [list(row) for row in rows] if rows else []

    def clear(self) -> None:
        self._rows = []

    def apply(self, kb: ReplyKeyboardMarkup) -> ReplyKeyboardMarkup:
        if not self._rows:
            return kb
        existing = {btn.text for row in kb.keyboard for btn in row}
        extra: list[list[KeyboardButton]] = []
        for row in self._rows:
            if any(btn.text in existing for btn in row):
                continue
            extra.append(list(row))
        if not extra:
            return kb
        rows = [list(r) for r in kb.keyboard] + extra
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=kb.resize_keyboard,
            input_field_placeholder=kb.input_field_placeholder,
            selective=kb.selective,
            one_time_keyboard=kb.one_time_keyboard,
            is_persistent=kb.is_persistent,
        )


_keyboard_extras = ReplyKeyboardExtras()


def clear_keyboard_extras() -> None:
    _keyboard_extras.clear()


def set_keyboard_extras(rows: list[list[KeyboardButton]] | None) -> None:
    _keyboard_extras.set(rows)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.core.pdmsg import pdmsg

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=pdmsg("auto_ca15d9d2aa"))]],
        resize_keyboard=True,
    )
    return _keyboard_extras.apply(kb)


def append_button_rows(
    kb: ReplyKeyboardMarkup,
    rows: list[list[KeyboardButton | str]],
) -> ReplyKeyboardMarkup:
    """Append rows to a keyboard without touching global extras (one-off composition)."""
    normalized: list[list[KeyboardButton]] = []
    for row in rows:
        normalized.append([btn if isinstance(btn, KeyboardButton) else KeyboardButton(text=btn) for btn in row])
    extras = ReplyKeyboardExtras()
    extras.set(normalized)
    return extras.apply(kb)


def get_routines_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=pmsg_menu("routines_stats")),
                KeyboardButton(text=pmsg_menu("routines_recommendations")),
            ],
            [KeyboardButton(text=pmsg_menu("routines_today"))],
            [KeyboardButton(text=pmsg_menu("back"))],
        ],
        resize_keyboard=True,
    )
    return _keyboard_extras.apply(kb)


def get_tasks_filter_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=pmsg_menu("goals")),
                KeyboardButton(text=pmsg_menu("priorities")),
            ],
            [KeyboardButton(text=pmsg_menu("statuses"))],
            [KeyboardButton(text=pmsg_menu("all_tasks"))],
            [KeyboardButton(text=pmsg_menu("back"))],
        ],
        resize_keyboard=True,
    )
    return _keyboard_extras.apply(kb)


def get_statuses_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.core.config import KANBAN_COLUMNS

    cols = KANBAN_COLUMNS
    rows: list[list[KeyboardButton]] = []
    for i in range(0, len(cols), 3):
        rows.append([KeyboardButton(text=cols[j]) for j in range(i, min(i + 3, len(cols)))])
    rows.append([KeyboardButton(text=pmsg_menu("back"))])
    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    return _keyboard_extras.apply(kb)


def get_categories_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.core.config import CATEGORIES

    prefix = pmsg_menu("category_prefix")
    category_buttons: list[list[KeyboardButton]] = []
    for i in range(0, len(CATEGORIES), 2):
        row: list[KeyboardButton] = []
        for j in range(2):
            if i + j < len(CATEGORIES):
                row.append(KeyboardButton(text=f"{prefix}{CATEGORIES[i + j]}"))
        if row:
            category_buttons.append(row)
    category_buttons.append([KeyboardButton(text=pmsg_menu("back"))])
    kb = ReplyKeyboardMarkup(keyboard=category_buttons, resize_keyboard=True)
    return _keyboard_extras.apply(kb)


def get_priorities_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=pmsg_menu("priority_high")),
                KeyboardButton(text=pmsg_menu("priority_medium")),
            ],
            [KeyboardButton(text=pmsg_menu("priority_low"))],
            [KeyboardButton(text=pmsg_menu("back"))],
        ],
        resize_keyboard=True,
    )
    return _keyboard_extras.apply(kb)
