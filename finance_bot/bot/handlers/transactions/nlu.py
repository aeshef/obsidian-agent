"""NLU handlers (voice via shared.telegram.host.wire.include_host_voice)."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state

from bot.config_loader import get_nlu_config, nlu_exact_commands, nlu_menu_buttons
from bot.ui import fmsg
from shared.i18n import msg
from shared.telegram.navigation import is_host_navigation
from bot.services.nlu_parser import TransactionNLUParser
from bot.services.transactions import get_missing_fields
from bot.handlers.transactions.confirmation import show_transaction_confirmation
from bot.handlers.transactions.states import AddTxnState, ConfirmTransactionsState

log = logging.getLogger("finance.transactions.nlu")
router = Router()


async def process_transactions(
    text: str,
    message: types.Message,
    state: FSMContext,
    write_context: Optional[dict] = None,
    *,
    enforce_write_context: bool = False,
    badge_defaults: Optional[dict] = None,
) -> None:
    """Parse text into one or more transactions and show confirmation.

    write_context: type/account/category from badge menu, wizard, etc.
    enforce_write_context: True overwrites NLU (button context wins).
    badge_defaults: alias for write_context + enforce (compat).
    """
    from bot.services.transactions import merge_write_context

    text = (text or "").strip()
    if is_host_navigation(text):
        await state.clear()
        from shared.telegram.host.keyboards import root_keyboard

        await message.answer(msg("host", "main_menu"), reply_markup=root_keyboard())
        return

    ctx = write_context or badge_defaults
    current_data = await state.get_data()
    badge_mode = bool(current_data.get("badge_mode"))

    if not badge_mode and not ctx:
        from bot.handlers.badge import badge_write_context, infer_badge_spend_text

        if infer_badge_spend_text(text):
            badge_mode = True
            ctx = badge_write_context()
            await state.update_data(badge_mode=True)

    enforce = enforce_write_context or badge_mode

    log.info(
        "process_transactions user=%s badge=%s enforce=%s text=%.80r",
        message.from_user.id,
        badge_mode,
        enforce,
        text,
    )

    current_state = await state.get_state()
    if current_state and str(current_state).startswith("ConfirmTransactionsState"):
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from bot.config_loader import nlu_cancel_texts
        from shared.telegram.host import labels as host_labels
        from shared.telegram.host.keyboards import root_keyboard
        from shared.i18n import msg as host_msg
        from shared.ui import common

        if is_host_navigation(text) or text == host_labels.back_home():
            await state.clear()
            await message.answer(host_msg("host", "main_menu"), reply_markup=root_keyboard())
            return
        cancel_lbl = common("cancel_button")
        if text == cancel_lbl or text.strip().lower() in nlu_cancel_texts():
            await state.clear()
            await message.answer(fmsg("confirm_cancelled"))
            return
        await message.answer(
            fmsg("nlu_pending_confirm"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=cancel_lbl, callback_data="txn:cancel")]
                ]
            ),
        )
        return

    parser = TransactionNLUParser()
    try:
        parsed_list = await parser.parse(text, telegram_id=message.from_user.id)
    except Exception as e:
        log.error("Transaction parse error: %s", e, exc_info=True)
        await message.answer(fmsg("nlu_parse_error", error=e, text=text))
        return

    log.info("parsed transactions count=%d badge=%s", len(parsed_list), badge_mode)

    if not parsed_list:
        log.warning("LLM did not recognize transaction from text: %r", text)
        await message.answer(fmsg("nlu_not_recognized", text=text))
        return

    if not badge_mode and not ctx:
        from bot.handlers.badge import badge_write_context, parsed_expenses_are_badge

        if parsed_expenses_are_badge(parsed_list):
            badge_mode = True
            ctx = badge_write_context()
            enforce = True
            await state.update_data(badge_mode=True)
            log.info("auto badge_mode from parsed category for user=%s", message.from_user.id)

    if ctx:
        for parsed in parsed_list:
            merge_write_context(parsed, ctx, enforce=enforce)

    if badge_mode:
        from bot.handlers.badge import ensure_badge_account, resolve_account_from_user_text

        await ensure_badge_account(message.from_user.id)
        for parsed in parsed_list:
            if await resolve_account_from_user_text(parsed, message.from_user.id, text):
                badge_mode = False
                enforce = False
                await state.update_data(badge_mode=False)
                log.info(
                    "badge_mode cleared: account %r from user text for user=%s",
                    parsed.get("account"),
                    message.from_user.id,
                )
                break

    for i, parsed in enumerate(parsed_list):
        try:
            missing = await get_missing_fields(
                parsed, message.from_user.id, badge_mode=badge_mode
            )
        except Exception as e:
            log.error(
                "Transaction check error %d/%d: %s",
                i + 1,
                len(parsed_list),
                e,
                exc_info=True,
            )
            await message.answer(
                fmsg(
                    "nlu_check_error",
                    index=i + 1,
                    total=len(parsed_list),
                    detail=str(e),
                )
            )
            return
        log.info(
            "Transaction %d missing fields: %s",
            i + 1,
            list(missing.keys()) if missing else "none",
        )
        if missing:
            log.warning("  need to fill: %s", ", ".join(missing.keys()))
        else:
            log.info("  all fields recognized")

    await state.set_state(ConfirmTransactionsState.transactions)
    await state.update_data(
        transactions=parsed_list,
        current_index=0,
        wizard_message_id=None,
        badge_mode=badge_mode,
    )

    try:
        await show_transaction_confirmation(
            parsed_list[0], message, state, 0, len(parsed_list)
        )
    except Exception as e:
        log.error("Confirmation display error: %s", e, exc_info=True)
        await message.answer(fmsg("nlu_confirm_error", count=len(parsed_list), error=e))
        await state.clear()


@router.message(~StateFilter(default_state), F.text)
async def handle_natural_language(message: types.Message, state: FSMContext) -> None:
    """Text outside default_state: NLU. In default_state financial_query routes here without duplicate."""
    text = message.text.strip()

    if text.startswith("/"):
        return

    nlu_cfg = get_nlu_config()
    if text in nlu_exact_commands(nlu_cfg):
        return

    if text in nlu_menu_buttons(nlu_cfg):
        log.info("Menu button %r — skipped (handled in start.py)", text)
        return

    current_state = await state.get_state()
    if current_state and current_state.startswith("AddTxnState"):
        log.info("Text in wizard state %s — clearing and routing to LLM", current_state)
        await state.clear()

    log.info("Routing text to LLM: %r", text)
    await process_transactions(text, message, state)
