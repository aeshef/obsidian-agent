"""Multi-transaction confirmation UI."""
from __future__ import annotations
from shared.finance.currency import base_currency

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.db import AsyncSessionLocal
from bot.models import User, Account
from bot.services.categories import load_categories
from bot.services.transactions import get_missing_fields, parse_occurred_at
from bot.ui import fmsg
from shared.ui import common

log = logging.getLogger("finance.transactions.confirmation")

_TXN_TYPE_KEYS = {
    "expense": "txn_type_expense",
    "income": "txn_type_income",
    "transfer": "txn_type_transfer",
    "debt_receivable": "txn_type_debt_receivable",
    "debt_payable": "txn_type_debt_payable",
    "debt_settle_receivable": "txn_type_debt_settle_receivable",
    "broker_withdraw": "txn_type_broker_withdraw",
    "account_balance": "txn_type_account_balance",
}


def _txn_type_label(txn_type: str) -> str:
    key = _TXN_TYPE_KEYS.get(txn_type)
    return fmsg(key, default=txn_type) if key else txn_type


async def show_transaction_confirmation(
    parsed: dict,
    message: Message,
    state: FSMContext,
    index: int,
    total: int,
    tg_id: Optional[int] = None,
) -> None:
    """Show transaction confirmation with buttons for missing fields."""
    if tg_id is None:
        if hasattr(message, "from_user") and message.from_user:
            tg_id = message.from_user.id
        elif hasattr(message, "chat"):
            tg_id = message.chat.id
        else:
            log.error("Cannot resolve tg_id from message type %s", type(message))
            return

    log.info("Show transaction %s of %s for user %s", index + 1, total, tg_id)

    data = await state.get_data()
    badge_mode = bool(data.get("badge_mode"))
    missing = await get_missing_fields(parsed, tg_id, badge_mode=badge_mode)

    lines = []
    if total > 1:
        lines.append(fmsg("confirm_preview_batch", index=index + 1, total=total))

    type_emoji = {
        "expense": "➖",
        "income": "➕",
        "transfer": "↔️",
        "debt_receivable": "💸",
        "debt_payable": "💸",
        "debt_settle_receivable": "💸",
        "broker_withdraw": "📈",
        "account_balance": "💳",
    }
    emoji = type_emoji.get(parsed.get("type", ""), "💰")
    lines.append(fmsg("confirm_preview_title", emoji=emoji))

    if parsed.get("amount"):
        lines.append(
            fmsg(
                "confirm_preview_amount",
                amount=parsed["amount"],
                currency=parsed.get("currency") or base_currency(),
            )
        )
    elif missing.get("amount"):
        lines.append(fmsg("confirm_preview_amount_missing"))

    if parsed.get("type"):
        lines.append(fmsg("confirm_preview_type", type_name=_txn_type_label(parsed["type"])))

    if parsed.get("category"):
        category_display = parsed.get("_found_category_name") or parsed.get("category")
        lines.append(fmsg("confirm_preview_category", category=category_display))
    elif missing.get("category"):
        lines.append(fmsg("confirm_preview_category_missing"))

    if parsed.get("account"):
        account_display = parsed.get("_found_account_name") or parsed.get("account")
        lines.append(fmsg("confirm_preview_account", account=account_display))
    elif missing.get("account"):
        lines.append(fmsg("confirm_preview_account_missing"))

    if parsed.get("from_account"):
        lines.append(fmsg("confirm_preview_from", account=parsed["from_account"]))
    elif missing.get("from_account"):
        lines.append(fmsg("confirm_preview_from_missing"))

    if parsed.get("to_account"):
        to_account_display = parsed.get("_found_to_account_name") or parsed.get("to_account")
        lines.append(fmsg("confirm_preview_to", account=to_account_display))
    elif missing.get("to_account"):
        lines.append(fmsg("confirm_preview_to_missing"))

    if parsed.get("type") == "broker_withdraw":
        raw_fee = parsed.get("fee")
        if raw_fee is not None:
            try:
                fee_dec = Decimal(str(raw_fee))
                if fee_dec > 0:
                    lines.append(
                        fmsg(
                            "confirm_preview_broker_fee",
                            fee=fee_dec,
                            currency=parsed.get("currency") or base_currency(),
                        )
                    )
                else:
                    lines.append(fmsg("confirm_preview_broker_fee_none"))
            except Exception:
                lines.append(fmsg("confirm_preview_broker_fee_raw", fee=raw_fee))

    if parsed.get("counterparty"):
        lines.append(fmsg("confirm_preview_counterparty", counterparty=parsed["counterparty"]))
    elif missing.get("counterparty"):
        lines.append(fmsg("confirm_preview_counterparty_missing"))

    if parsed.get("description"):
        lines.append(fmsg("confirm_preview_description", description=parsed["description"]))

    occ = parse_occurred_at(parsed)
    occ_date_str = occ.strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    if occ_date_str != today_str:
        lines.append(fmsg("confirm_preview_date", date=occ_date_str))
    else:
        lines.append(fmsg("confirm_preview_date_today"))

    text = "\n".join(lines)

    kb_rows = []

    if missing.get("amount"):
        kb_rows.append(
            [InlineKeyboardButton(text=fmsg("confirm_btn_set_amount"), callback_data=f"txn:set_amount:{index}")]
        )

    if missing.get("category"):
        if parsed.get("type") in ["expense", "income"]:
            kind = "expense" if parsed.get("type") == "expense" else "income"
            cats = load_categories(kind)
            for i in range(0, min(6, len(cats)), 2):
                row = []
                if i < len(cats):
                    row.append(
                        InlineKeyboardButton(text=cats[i], callback_data=f"txn:set_cat:{index}:{cats[i]}")
                    )
                if i + 1 < len(cats):
                    row.append(
                        InlineKeyboardButton(
                            text=cats[i + 1], callback_data=f"txn:set_cat:{index}:{cats[i + 1]}"
                        )
                    )
                if row:
                    kb_rows.append(row)
            if len(cats) > 6:
                kb_rows.append(
                    [
                        InlineKeyboardButton(
                            text=fmsg("confirm_btn_set_category"),
                            callback_data=f"txn:set_cat_text:{index}",
                        )
                    ]
                )

    if missing.get("account"):
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == tg_id))
            ).scalar_one_or_none()
            if not user:
                log.error("User %s not found when building account buttons", tg_id)
                return
            accounts = (
                await session.execute(
                    select(Account).where(Account.user_id == user.id, Account.is_external_balance == False)
                )
            ).scalars().all()
            for i in range(0, min(6, len(accounts)), 2):
                row = []
                if i < len(accounts):
                    row.append(
                        InlineKeyboardButton(
                            text=accounts[i].name, callback_data=f"txn:set_acc:{index}:{accounts[i].id}"
                        )
                    )
                if i + 1 < len(accounts):
                    row.append(
                        InlineKeyboardButton(
                            text=accounts[i + 1].name,
                            callback_data=f"txn:set_acc:{index}:{accounts[i + 1].id}",
                        )
                    )
                if row:
                    kb_rows.append(row)

    if missing.get("from_account"):
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == tg_id))
            ).scalar_one_or_none()
            if user:
                accounts = (
                    await session.execute(select(Account).where(Account.user_id == user.id))
                ).scalars().all()
                for i in range(0, min(6, len(accounts)), 2):
                    row = []
                    if i < len(accounts):
                        row.append(
                            InlineKeyboardButton(
                                text=accounts[i].name,
                                callback_data=f"txn:set_from:{index}:{accounts[i].id}",
                            )
                        )
                    if i + 1 < len(accounts):
                        row.append(
                            InlineKeyboardButton(
                                text=accounts[i + 1].name,
                                callback_data=f"txn:set_from:{index}:{accounts[i + 1].id}",
                            )
                        )
                    if row:
                        kb_rows.append(row)

    if missing.get("to_account"):
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == tg_id))
            ).scalar_one_or_none()
            if user:
                accounts = (
                    await session.execute(select(Account).where(Account.user_id == user.id))
                ).scalars().all()
                for i in range(0, min(6, len(accounts)), 2):
                    row = []
                    if i < len(accounts):
                        row.append(
                            InlineKeyboardButton(
                                text=accounts[i].name,
                                callback_data=f"txn:set_to:{index}:{accounts[i].id}",
                            )
                        )
                    if i + 1 < len(accounts):
                        row.append(
                            InlineKeyboardButton(
                                text=accounts[i + 1].name,
                                callback_data=f"txn:set_to:{index}:{accounts[i + 1].id}",
                            )
                        )
                    if row:
                        kb_rows.append(row)

    if missing.get("counterparty"):
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=fmsg("confirm_btn_set_counterparty"),
                    callback_data=f"txn:set_counterparty:{index}",
                )
            ]
        )

    if not missing:
        kb_rows.append([InlineKeyboardButton(text=fmsg("wizard_confirm_btn"), callback_data=f"txn:confirm:{index}")])

    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton(text=fmsg("confirm_btn_prev"), callback_data=f"txn:prev:{index}"))
    if index < total - 1:
        nav_row.append(InlineKeyboardButton(text=fmsg("confirm_btn_next"), callback_data=f"txn:next:{index}"))
    if nav_row:
        kb_rows.append(nav_row)

    kb_rows.append([InlineKeyboardButton(text=common("cancel_button"), callback_data="txn:cancel")])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    if hasattr(message, "bot"):
        bot = message.bot
    else:
        log.error("Cannot resolve bot from message type %s", type(message))
        return

    chat_id = message.chat.id if hasattr(message, "chat") else None
    if not chat_id:
        log.error("Cannot resolve chat_id from message type %s", type(message))
        return

    msg_id = data.get("wizard_message_id")

    log.debug("Edit message: msg_id=%s chat_id=%s index=%s total=%s", msg_id, chat_id, index, total)

    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML",
            )
            log.debug("Message %s edited", msg_id)
            return
        except Exception as e:
            log.warning("Failed to edit message %s: %s, sending new", msg_id, e)

    log.debug("Send new message to chat_id=%s", chat_id)
    # Plain HTML only — Rich Messages + edit_message_text leave a stale rich
    # snapshot above the edited body (Telegram client bug).
    m = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="HTML")
    await state.update_data(wizard_message_id=m.message_id)
    log.debug("New message %s saved in state", m.message_id)
