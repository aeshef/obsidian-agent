"""Balance view."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Tuple

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import select, func

from bot.handlers.start import main_menu_inline
from bot.db import AsyncSessionLocal
from bot.models import User, Account, Transaction
from bot.services.badge_tracker import is_badge_account_name
from bot.services.transactions.core import is_cash_wallet_name
from bot.services.crypto_prices import fetch_prices_rub
from bot.ui import fmsg
from shared.ui import common

log = logging.getLogger("finance.transactions.balance")
router = Router()


async def _render_balance(tg_id: int) -> Tuple[str, types.InlineKeyboardMarkup]:
    """Build balance text and keyboard."""
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if user is None:
            return common("need_start"), None

        accounts = (await session.execute(select(Account).where(Account.user_id == user.id))).scalars().all()

        async def acc_balance(acc: Account) -> Decimal:
            inc = (
                await session.execute(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.account_id == acc.id, Transaction.type == "income"
                    )
                )
            ).scalar_one()
            exp = (
                await session.execute(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.account_id == acc.id, Transaction.type == "expense"
                    )
                )
            ).scalar_one()
            from_txn = Decimal(inc) - Decimal(exp)
            if acc.is_external_balance and acc.external_balance is not None:
                return Decimal(acc.external_balance)
            base = Decimal(acc.external_balance) if acc.external_balance is not None else Decimal(0)
            return base + from_txn

        groups = {
            "cards": [],
            "invest": [],
            "crypto": [],
            "debts": [],
            "cash": [],
        }
        crypto_symbols: set[str] = set()
        for a in accounts:
            if a.type == "crypto":
                crypto_symbols.add(a.currency.upper())
        prices_rub = {}
        if crypto_symbols:
            prices_rub = await fetch_prices_rub(sorted(list(crypto_symbols)))

        for acc in accounts:
            if is_badge_account_name(acc.name):
                continue
            bal = await acc_balance(acc)
            entry = (acc, bal)
            if acc.type in ("card",) or (
                acc.type == "wallet" and not is_cash_wallet_name(acc.name)
            ):
                if bal != 0:
                    groups["cards"].append(entry)
            elif acc.type == "wallet":
                if bal != 0:
                    groups["cash"].append(entry)
            elif acc.type.startswith("broker"):
                if bal != 0:
                    groups["invest"].append(entry)
            elif acc.type == "crypto":
                groups["crypto"].append(entry)
            elif acc.type in ("receivable", "liability_payable"):
                if bal != 0:
                    groups["debts"].append(entry)
            else:
                if bal != 0:
                    groups["cards"].append(entry)

        def fmt_line(acc: Account, amount: Decimal) -> str:
            label_raw = acc.name
            short_name = acc.name.split(":", 1)[-1]
            if acc.type == "receivable":
                label_raw = fmsg("balance_debt_receivable_label", name=short_name)
            elif acc.type == "liability_payable":
                label_raw = fmsg("balance_debt_payable_label", name=short_name)
            label = label_raw[:24]
            if acc.type == "crypto":
                sym = acc.currency.upper()
                amt_crypto = f"{amount:.8f} {sym}"
                rub_val = None
                if sym in prices_rub:
                    rub_val = float(amount) * float(prices_rub[sym])
                rub_str = f" (~{rub_val:.2f} RUB)" if rub_val is not None else ""
                return f"{label:<24} {amt_crypto}{rub_str}"
            amt = f"{amount:.2f}" if acc.currency in ("RUB", "RUR", "USD", "EUR", "GBP", "CNY") else f"{amount:.6f}"
            return f"{label:<24} {amt:>14} {acc.currency}"

        sections: List[str] = []

        def add_section(title: str, items: List[Tuple[Account, Decimal]]):
            if not items:
                return
            sections.append(title)
            for acc, bal in items:
                sections.append(fmt_line(acc, bal))
            sections.append("")

        sections.append(fmsg("balance_title"))
        sections.append("<pre>")
        add_section(fmsg("balance_section_cards"), groups["cards"])
        add_section(fmsg("balance_section_cash"), groups["cash"])
        add_section(fmsg("balance_section_invest"), groups["invest"])
        add_section(fmsg("balance_section_crypto"), groups["crypto"])
        add_section(fmsg("balance_section_debts"), groups["debts"])

        if len(sections) == 2:
            has_any_accounts = len(accounts) > 0
            if has_any_accounts:
                sections.append(fmsg("balance_all_zero"))
            else:
                sections.append(fmsg("balance_no_accounts"))
                sections.append("")
                sections.append(fmsg("balance_add_account_hint"))
                sections.append(fmsg("balance_add_account_path"))

        if sections and sections[-1] == "":
            sections.pop()
        sections.append("</pre>")

        text = "\n".join(sections)
        log.info(
            "Balance rendered for user %s: %s cards, %s invest",
            tg_id,
            len(groups["cards"]),
            len(groups["invest"]),
        )
        return text, main_menu_inline()


@router.callback_query(F.data == "action:balance")
async def show_balance_cb(callback: types.CallbackQuery) -> None:
    """Show balance from inline button."""
    try:
        log.info("Balance request from user %s", callback.from_user.id)
        text, kb = await _render_balance(callback.from_user.id)
        log.info("Balance text length=%s", len(text))
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            log.info("Balance message edited")
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                log.error("Balance edit failed: %s", e)
                await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            log.error("Balance edit error: %s", e, exc_info=True)
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        log.error("Balance render error: %s", e, exc_info=True)
        await callback.answer(common("error", error=e), show_alert=True)
    await callback.answer()
