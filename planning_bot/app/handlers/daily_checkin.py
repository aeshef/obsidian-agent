"""Telegram daily close: routines + subjective signals."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from planning_bot.app import keyboards
from planning_bot.app.states import DailyCheckinState
from planning_bot.app.ui import pmsg
from planning_bot.services.checkin_state import (
    mark_completed,
    mark_prompt_sent,
    mark_snooze,
    should_send_scheduled_prompt,
)
from planning_bot.services.daily_checkin import (
    RoutineItem,
    SignalItem,
    apply_routine_answer,
    build_routine_queue,
    build_signal_queue,
    category_keyboard,
    completion_summary,
    offer_keyboard,
    resolve_category_index,
    routine_keyboard,
    routine_prompt_text,
    scale_keyboard,
    signal_prompt_text,
)
from planning_bot.services.daily_checkin_config import checkin_snooze_minutes as cfg_snooze
from planning_bot.services.ritual_day import ritual_day_date
from planning_bot.services.routines_manager import ensure_routines_bucket
from planning_bot.services.signals_manager import append_signals_entry, ensure_signals_layout
from shared.ritual_day import parse_close_date

logger = logging.getLogger(__name__)

_STATE_ROUTINES = "routines"
_STATE_SIGNALS = "signals"


def _serialize_routines(queue: list[RoutineItem]) -> list[dict[str, Any]]:
    return [
        {"section": x.section, "task": x.task, "already_done": x.already_done}
        for x in queue
    ]


def _deserialize_routines(raw: list[Any]) -> list[RoutineItem]:
    out: list[RoutineItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            RoutineItem(
                section=str(item.get("section", "")),
                task=str(item.get("task", "")),
                already_done=bool(item.get("already_done")),
            )
        )
    return out


def _serialize_signals(queue: list[SignalItem]) -> list[dict[str, Any]]:
    return [
        {
            "signal_id": x.signal_id,
            "kind": x.kind,
            "scale": x.scale,
            "question_key": x.question_key,
        }
        for x in queue
    ]


def _deserialize_signals(raw: list[Any]) -> list[SignalItem]:
    out: list[SignalItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            SignalItem(
                signal_id=str(item.get("signal_id", "")),
                kind=str(item.get("kind", "scale")),
                scale=item.get("scale"),
                question_key=str(item.get("question_key", "")),
            )
        )
    return out


async def start_daily_checkin(self, message: Message, state: FSMContext) -> None:
    await _begin_checkin(message, state)


async def send_daily_checkin_prompt(bot: Bot, chat_id: int) -> bool:
    if not should_send_scheduled_prompt():
        return False
    mark_prompt_sent()
    day = ritual_day_date()
    from shared.i18n import msg
    from shared.telegram.push_format import format_push, send_push

    # Same card envelope as finance evening / morning brief (# title + body).
    text = format_push(
        msg("push", "checkin_title") or msg("push", "section_evening_routines"),
        pmsg("checkin_offer", date=day),
        footer=day,
    )
    await send_push(bot, chat_id, text, reply_markup=offer_keyboard())
    return True


async def _begin_checkin(
    message: Message,
    state: FSMContext,
    *,
    close_date: str | None = None,
) -> None:
    day = parse_close_date(close_date or "") or ritual_day_date()
    ensure_signals_layout()
    ensure_routines_bucket(day)
    routines = build_routine_queue()
    signals = build_signal_queue()
    await state.set_state(DailyCheckinState.active)
    await state.update_data(
        close_date=day,
        phase=_STATE_ROUTINES if routines else _STATE_SIGNALS,
        routine_queue=_serialize_routines(routines),
        signal_queue=_serialize_signals(signals),
        routine_index=0,
        signal_index=0,
        signal_answers={},
    )
    if routines:
        await _send_routine_step(message, state)
    elif signals:
        await message.answer(pmsg("checkin_signals_intro"))
        await _send_signal_step(message, state)
    else:
        await _finish(message, state)


async def _send_routine_step(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    queue = _deserialize_routines(data.get("routine_queue") or [])
    idx = int(data.get("routine_index", 0))
    if idx >= len(queue):
        await state.update_data(phase=_STATE_SIGNALS, signal_index=0)
        msg = target.message if isinstance(target, CallbackQuery) else target
        signals = _deserialize_signals((await state.get_data()).get("signal_queue") or [])
        if signals:
            await msg.answer(pmsg("checkin_signals_intro"))
            await _send_signal_step(msg, state)
        else:
            await _finish(msg, state)
        return
    item = queue[idx]
    text = routine_prompt_text(item, idx + 1, len(queue))
    kb = routine_keyboard(item.section, idx)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


async def _send_signal_step(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    queue = _deserialize_signals(data.get("signal_queue") or [])
    idx = int(data.get("signal_index", 0))
    if idx >= len(queue):
        msg = target.message if isinstance(target, CallbackQuery) else target
        await _finish(msg, state)
        return
    item = queue[idx]
    text = signal_prompt_text(item)
    if item.kind == "category_choice":
        kb = category_keyboard(idx)
    else:
        kb = scale_keyboard(idx, item.scale or "likert_5")
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


async def _finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    close_date = str(data.get("close_date") or ritual_day_date())
    answers = dict(data.get("signal_answers") or {})
    if answers:
        append_signals_entry(answers, date_str=close_date)
    mark_completed(close_date)
    await state.clear()
    await message.answer(
        completion_summary(answers, close_date),
        reply_markup=keyboards.get_main_keyboard(),
    )


async def handle_checkin_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if not data.startswith("chk:"):
        await callback.answer()
        return

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "go":
        offer_day = parse_close_date(parts[2]) if len(parts) >= 3 else None
        await _begin_checkin(
            callback.message,
            state,
            close_date=offer_day if offer_day else None,
        )
        return

    if action == "gd" and len(parts) >= 3:
        day = parse_close_date(parts[2])
        if day:
            await _begin_checkin(callback.message, state, close_date=day)
        return

    if action == "snooze":
        mark_snooze(cfg_snooze())
        await state.clear()
        await callback.message.edit_text(pmsg("checkin_snoozed"))
        await callback.answer()
        return

    if action == "skip":
        day = parse_close_date(parts[2]) if len(parts) >= 3 else ritual_day_date()
        mark_completed(day)
        await state.clear()
        await callback.message.edit_text(pmsg("checkin_skipped_today"))
        await callback.answer()
        return

    st = await state.get_state()
    if st != DailyCheckinState.active:
        if action == "go":
            pass
        else:
            await callback.answer(pmsg("checkin_session_expired"), show_alert=True)
            return

    phase = (await state.get_data()).get("phase")

    if action == "r" and len(parts) >= 5:
        try:
            task_index = int(parts[3])
            done = parts[4] == "1"
        except ValueError:
            await callback.answer()
            return
        queue = _deserialize_routines((await state.get_data()).get("routine_queue") or [])
        apply_routine_answer(queue, task_index, done)
        await state.update_data(routine_index=task_index + 1)
        await _send_routine_step(callback, state)
        return

    if action == "rs" and len(parts) >= 3:
        sec_code = parts[2]
        sec_map = {"m": "morning", "d": "day", "e": "evening"}
        section = sec_map.get(sec_code, "")
        data_s = await state.get_data()
        queue = _deserialize_routines(data_s.get("routine_queue") or [])
        idx = int(data_s.get("routine_index", 0))
        while idx < len(queue) and queue[idx].section == section:
            idx += 1
        await state.update_data(routine_index=idx)
        await _send_routine_step(callback, state)
        return

    if action == "s" and len(parts) >= 4:
        try:
            sig_index = int(parts[2])
            value = int(parts[3])
        except ValueError:
            await callback.answer()
            return
        data_s = await state.get_data()
        queue = _deserialize_signals(data_s.get("signal_queue") or [])
        if sig_index < len(queue):
            sid = queue[sig_index].signal_id
            answers = dict(data_s.get("signal_answers") or {})
            answers[sid] = value
            await state.update_data(signal_answers=answers, signal_index=sig_index + 1)
        await _send_signal_step(callback, state)
        return

    if action == "c" and len(parts) >= 4:
        try:
            sig_index = int(parts[2])
            cat_index = int(parts[3])
        except ValueError:
            await callback.answer()
            return
        data_s = await state.get_data()
        queue = _deserialize_signals(data_s.get("signal_queue") or [])
        if sig_index < len(queue):
            sid = queue[sig_index].signal_id
            answers = dict(data_s.get("signal_answers") or {})
            answers[sid] = resolve_category_index(cat_index)
            await state.update_data(signal_answers=answers, signal_index=sig_index + 1)
        await _send_signal_step(callback, state)
        return

    await callback.answer()
