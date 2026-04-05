"""Aiogram router: host commands and multi-domain text dispatch."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message

from shared.memory import clear_all_history, clear_history
from shared.agent.llm_classify import LLMClassificationError
from shared.telegram.host.constants import (
    DOMAIN_FINANCE,
    DOMAIN_IDS,
    DOMAIN_KNOWLEDGE,
    DOMAIN_PLANNING,
    UI_MODE_AUTO,
)
from shared.telegram.host.dispatch import switch_mode
from shared.i18n import msg, msgf
from shared.telegram.host import labels as L
from shared.telegram.host.keyboards import keyboard_for_mode, root_keyboard
from shared.telegram.host.menus import (
    is_finance_menu,
    is_knowledge_menu,
    is_planning_menu,
    mode_from_button,
)
from shared.telegram.messaging import send_long_message
from shared.telegram_utils import strip_telegram_markdown

log = logging.getLogger("shared.telegram.host")

router = Router(name="host")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(ui_mode=UI_MODE_AUTO)
    await message.answer(msg("host", "start_welcome"), reply_markup=root_keyboard())


@router.message(Command("domain"))
async def cmd_domain(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").split(maxsplit=1)
    data = await state.get_data()
    cur = data.get("ui_mode", UI_MODE_AUTO)
    uid = message.chat.id
    kb = root_keyboard() if cur == UI_MODE_AUTO else keyboard_for_mode(cur, user_id=uid)

    if len(parts) < 2:
        await message.answer(
            msgf(
                "host",
                "domain_current",
                mode=cur,
                finance=L.mode_finance(),
                planning=L.mode_planning(),
            ),
            reply_markup=kb,
        )
        return
    dom = parts[1].strip().lower()
    if dom == "auto":
        await switch_mode(message, state, UI_MODE_AUTO)
        return
    if dom not in DOMAIN_IDS:
        await message.answer(msg("host", "domain_invalid"), reply_markup=kb)
        return
    from shared.capabilities.profile import (
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        get_capabilities,
    )

    prof = get_capabilities()
    module_for = {
        DOMAIN_FINANCE: MODULE_FINANCE,
        DOMAIN_PLANNING: MODULE_PLANNING,
        DOMAIN_KNOWLEDGE: MODULE_KNOWLEDGE,
    }
    if dom in module_for and not prof.module(module_for[dom]):
        await message.answer(
            msg("host", "domain_unavailable"),
            reply_markup=kb,
        )
        return
    await switch_mode(message, state, dom)


@router.message(Command("bulk"))
async def cmd_bulk_on(message: Message, state: FSMContext) -> None:
    from shared.capabilities.registry import knowledge_module_enabled

    if not knowledge_module_enabled():
        await message.answer(
            msg("host", "knowledge_domain_unavailable"),
            reply_markup=root_keyboard(),
        )
        return
    from knowledge_bot.app.handlers.modes import enable_bulk_ingest

    from shared.telegram.host.keyboards import knowledge_keyboard

    await enable_bulk_ingest(
        message, reply_markup=knowledge_keyboard(bulk_active=True), state=state
    )


@router.message(Command("bulk_off"))
async def cmd_bulk_off(message: Message, state: FSMContext) -> None:
    from shared.capabilities.registry import knowledge_module_enabled

    if not knowledge_module_enabled():
        await message.answer(
            msg("host", "knowledge_domain_unavailable"),
            reply_markup=root_keyboard(),
        )
        return
    from knowledge_bot.app.handlers.modes import disable_bulk_ingest

    data = await state.get_data()
    ui_mode = data.get("ui_mode", UI_MODE_AUTO)
    kb_mode = ui_mode if ui_mode in DOMAIN_IDS else DOMAIN_KNOWLEDGE
    await disable_bulk_ingest(
        message,
        reply_markup=keyboard_for_mode(kb_mode, user_id=message.chat.id),
        state=state,
    )


@router.message(Command("reset", "reset_context"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    mode = data.get("ui_mode", UI_MODE_AUTO)
    if mode in DOMAIN_IDS:
        clear_history(message.chat.id, mode)
    else:
        clear_all_history(message.chat.id)
    await message.answer(
        msg("host", "history_cleared"),
        reply_markup=keyboard_for_mode(mode, user_id=message.chat.id),
    )


@router.message(StateFilter(default_state), F.text)
async def handle_text(
    message: Message, state: FSMContext, agent_app, planning=None
) -> None:
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    data = await state.get_data()
    ui_mode = data.get("ui_mode", UI_MODE_AUTO)
    uid = message.from_user.id if message.from_user else message.chat.id
    try:
        from knowledge_bot.app.state import is_bulk_ingest

        bulk_on = is_bulk_ingest(uid)
    except Exception:
        bulk_on = False
    fsm_state = await state.get_state()
    log.info(
        "host_text chat=%s ui_mode=%s bulk=%s fsm=%s len=%d",
        uid,
        ui_mode,
        bulk_on,
        fsm_state,
        len(text),
    )

    if text == L.back_home():
        await state.update_data(ui_mode=UI_MODE_AUTO, fixed_domain=None)
        await message.answer(msg("host", "main_menu"), reply_markup=root_keyboard())
        return

    new_mode = mode_from_button(text)
    if new_mode:
        await switch_mode(message, state, new_mode)
        return

    if agent_app.has_domain(DOMAIN_FINANCE) and (
        ui_mode == DOMAIN_FINANCE or (ui_mode == UI_MODE_AUTO and is_finance_menu(text))
    ):
        if ui_mode != DOMAIN_FINANCE:
            await state.update_data(ui_mode=DOMAIN_FINANCE, fixed_domain=DOMAIN_FINANCE)
        if is_finance_menu(text):
            from bot.reply_menu import dispatch_reply_menu_button

            if await dispatch_reply_menu_button(message, state):
                return
        from bot.handlers.financial_query import handle_smart_text

        await handle_smart_text(message, state, agent_app=agent_app)
        return

    if agent_app.has_domain(DOMAIN_PLANNING) and (
        ui_mode == DOMAIN_PLANNING or (ui_mode == UI_MODE_AUTO and is_planning_menu(text))
    ):
        if planning is None:
            await message.answer(
                msgf(
                    "host",
                    "planning_unavailable",
                    finance=L.mode_finance(),
                    knowledge=L.mode_knowledge(),
                ),
                reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
            )
            return
        if ui_mode != DOMAIN_PLANNING:
            await state.update_data(ui_mode=DOMAIN_PLANNING, fixed_domain=DOMAIN_PLANNING)
        from planning_bot.app.handlers import commands as planning_commands

        await planning_commands.process_user_text(
            planning, message, state, text, agent_app=agent_app
        )
        return

    if agent_app.has_domain(DOMAIN_KNOWLEDGE) and ui_mode == DOMAIN_KNOWLEDGE:
        from shared.telegram.host.knowledge_dispatch import try_handle_knowledge_text

        await try_handle_knowledge_text(message, agent_app, state=state)
        return

    from knowledge_bot.app.state import BTN_BULK_OFF, BTN_BULK_ON

    if agent_app.has_domain(DOMAIN_KNOWLEDGE) and is_knowledge_menu(text):
        # Legacy KB keyboard after home — still route to knowledge mode
        if ui_mode != DOMAIN_KNOWLEDGE:
            await switch_mode(message, state, DOMAIN_KNOWLEDGE)
        from knowledge_bot.app.handlers.modes import disable_bulk_ingest, enable_bulk_ingest
        from shared.telegram.host.keyboards import knowledge_keyboard
        from shared.telegram.host.knowledge_dispatch import try_handle_knowledge_text

        if text == BTN_BULK_ON:
            await enable_bulk_ingest(
                message, reply_markup=knowledge_keyboard(bulk_active=True), state=state
            )
            return
        if text == BTN_BULK_OFF:
            await disable_bulk_ingest(
                message, reply_markup=knowledge_keyboard(bulk_active=False), state=state
            )
            return
        await try_handle_knowledge_text(message, agent_app, state=state)
        return

    uid = message.chat.id
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        from shared.telegram.host.auto_dispatch import dispatch_auto_free_text

        await dispatch_auto_free_text(message, state, agent_app, text)
    except LLMClassificationError as e:
        log.error("host LLM routing failed: %s", e, exc_info=True)
        await message.answer(
            msgf("host", "llm_routing_failed", error=e),
            reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
        )
    except Exception as e:
        log.error("host auto dispatch failed: %s", e, exc_info=True)
        await message.answer(
            msgf("host", "agent_error", error=e),
            reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
        )
