"""Composable reply keyboards for Telegram bots."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


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


def compact_keyboard_rows(rows: list[list[KeyboardButton | str]]) -> list[list[KeyboardButton]]:
    """Drop buttons with empty labels and remove empty rows (CAP-gated msg() returns '')."""
    out: list[list[KeyboardButton]] = []
    for row in rows:
        buttons: list[KeyboardButton] = []
        for btn in row:
            if isinstance(btn, KeyboardButton):
                text = (btn.text or "").strip()
                if text:
                    buttons.append(btn)
            else:
                text = (btn or "").strip()
                if text:
                    buttons.append(KeyboardButton(text=text))
        if buttons:
            out.append(buttons)
    return out


def reply_keyboard_from_rows(
    rows: list[list[KeyboardButton | str]],
    *,
    resize_keyboard: bool = True,
    input_field_placeholder: str | None = None,
    **kwargs: object,
) -> ReplyKeyboardMarkup:
    compact = compact_keyboard_rows(rows)
    return ReplyKeyboardMarkup(
        keyboard=compact,
        resize_keyboard=resize_keyboard,
        input_field_placeholder=input_field_placeholder,
        **kwargs,
    )


def compact_reply_keyboard(kb: ReplyKeyboardMarkup) -> ReplyKeyboardMarkup:
    """Remove CAP-gated empty buttons from an existing keyboard."""
    rows = [[btn for btn in row] for row in kb.keyboard]
    compact = compact_keyboard_rows(rows)
    if compact == kb.keyboard:
        return kb
    return ReplyKeyboardMarkup(
        keyboard=compact,
        resize_keyboard=kb.resize_keyboard,
        input_field_placeholder=kb.input_field_placeholder,
        selective=kb.selective,
        one_time_keyboard=kb.one_time_keyboard,
        is_persistent=kb.is_persistent,
    )


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
