"""Transaction confirmation handlers."""
from shared.finance.currency import base_currency
from decimal import Decimal
import logging

from aiogram import types
from sqlalchemy import select

from bot.ui import fmsg
from shared.domain_messages import dmsg
from shared.ui import common

from bot.models import User, Account, Transaction
from bot.handlers.transactions import _parse_occurred_at

log = logging.getLogger("finance.transactions.confirm")

async def _process_confirmed_transaction(
    session,
    user: User,
    parsed: dict,
    callback: types.CallbackQuery,
    *,
    badge_mode: bool = False,
) -> bool:
    """Process confirmed transaction and persist to DB."""
    # account_balance
    if parsed.get("type") == "account_balance":
        account_name = parsed.get("account", fmsg("default_wallet_name"))
        balance = Decimal(str(parsed.get("balance", 0)))
        currency = parsed.get("currency") or base_currency()
        
        existing = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.name == account_name))
        ).scalar_one_or_none()
        
        if existing:
            existing.external_balance = balance
            existing.currency = currency
        else:
            from bot.services.transactions.core import infer_account_type

            acc_type = infer_account_type(account_name)
            account = Account(
                user_id=user.id,
                name=account_name,
                type=acc_type,
                currency=currency,
                is_external_balance=True,
                external_balance=balance,
            )
            session.add(account)
        
        await session.commit()
        await callback.answer(fmsg("confirm_account_updated_name", name=account_name))
        return True
    
    # broker_withdraw
    if parsed.get("type") == "broker_withdraw":
        from bot.handlers.transactions import _handle_broker_withdraw
        await _handle_broker_withdraw(session, user, parsed, callback.message)
        await session.commit()
        await callback.answer(fmsg("confirm_broker_withdraw"))
        return True
    
    # debt_settle_receivable
    if parsed.get("type") == "debt_settle_receivable":
        from bot.handlers.transactions import _get_or_create_account
        from bot.handlers.debts import _upsert_debt_account

        counterparty = parsed.get("counterparty") or dmsg("finance", "unknown_counterparty")
        amount = Decimal(str(parsed.get("amount", 0)))
        currency = parsed.get("currency") or base_currency()
        account_name = parsed.get("_found_account_name") or parsed.get("account")
        if not account_name:
            await callback.answer(fmsg("confirm_no_credit_account"), show_alert=True)
            return False

        to_acc = await _get_or_create_account(session, user.id, account_name)
        if to_acc.currency != currency:
            await callback.answer(
                common("account_currency_mismatch", account_currency=to_acc.currency, currency=currency),
                show_alert=True,
            )
            return False

        debt_acc = await _upsert_debt_account(session, user.id, "settle_recv", counterparty, currency)
        cur = Decimal(debt_acc.external_balance or 0)
        debt_acc.external_balance = max(Decimal("0"), cur - amount)

        occurred = _parse_occurred_at(parsed)
        session.add(Transaction(
            user_id=user.id,
            account_id=to_acc.id,
            type="income",
            amount=amount,
            currency=to_acc.currency,
            category=dmsg("finance", "debts_category"),
            description=dmsg("finance", "debt_return_description", counterparty=counterparty),
            occurred_at=occurred,
        ))
        await session.commit()
        await callback.answer(
            fmsg(
                "confirm_debt_recorded",
                counterparty=counterparty,
                amount=amount,
                currency=currency,
                to_account=to_acc.name,
            )
        )
        return True

    # debt_receivable / debt_payable
    if parsed.get("type") in ["debt_receivable", "debt_payable"]:
        from bot.handlers.debts import _upsert_debt_account
        from bot.handlers.transactions import _get_or_create_account

        counterparty = parsed.get("counterparty") or dmsg("finance", "unknown_counterparty")
        amount = Decimal(str(parsed.get("amount", 0)))
        currency = parsed.get("currency") or base_currency()
        mode = "recv" if parsed.get("type") == "debt_receivable" else "pay"

        if mode == "recv":
            account_name = parsed.get("_found_account_name") or parsed.get("account")
            if not account_name:
                await callback.answer(fmsg("confirm_no_debit_account"), show_alert=True)
                return False
            from_acc = await _get_or_create_account(session, user.id, account_name)
            if from_acc.currency != currency:
                await callback.answer(
                    common("account_currency_mismatch", account_currency=from_acc.currency, currency=currency),
                    show_alert=True,
                )
                return False

            occurred = _parse_occurred_at(parsed)
            session.add(Transaction(
                user_id=user.id,
                account_id=from_acc.id,
                type="expense",
                amount=amount,
                currency=from_acc.currency,
                category=dmsg("finance", "debts_category"),
                description=dmsg("finance", "debt_issue_description", counterparty=counterparty),
                occurred_at=occurred,
            ))

        acc = await _upsert_debt_account(session, user.id, mode, counterparty, currency)
        cur = Decimal(acc.external_balance or 0)
        acc.external_balance = cur + amount

        await session.commit()
        if mode == "recv":
            msg = fmsg(
                "confirm_debt_recorded_recv",
                counterparty=counterparty,
                amount=amount,
                currency=currency,
                account=account_name,
            )
        else:
            msg = fmsg(
                "confirm_debt_recorded_simple",
                counterparty=counterparty,
                amount=amount,
                currency=currency,
            )
        await callback.answer(msg)
        return True
    
    # expense / income / transfer
    if parsed.get("type") in ["expense", "income", "transfer"]:
        from bot.handlers.transactions import _get_or_create_account
        
        occurred = _parse_occurred_at(parsed)
        if parsed.get("type") == "transfer":
            from_acc = await _get_or_create_account(session, user.id, parsed.get("from_account"))
            to_acc = await _get_or_create_account(session, user.id, parsed.get("to_account"))
            amount = Decimal(str(parsed["amount"]))
            
            # debit from_account
            session.add(Transaction(
                user_id=user.id,
                account_id=from_acc.id,
                type="expense",
                amount=amount,
                currency=from_acc.currency,
                category=dmsg("finance", "transfer_category"),
                description=dmsg("finance", "transfer_to_description", account=to_acc.name),
                occurred_at=occurred,
            ))
            
            # credit to_account
            session.add(Transaction(
                user_id=user.id,
                account_id=to_acc.id,
                type="income",
                amount=amount,
                currency=to_acc.currency,
                category=dmsg("finance", "transfer_category"),
                description=dmsg("finance", "transfer_from_description", account=from_acc.name),
                occurred_at=occurred,
            ))
        else:
            from bot.services.transactions import resolve_expense_account

            account = await resolve_expense_account(
                session, user.id, parsed, badge_mode=badge_mode
            )
            
            txn = Transaction(
                user_id=user.id,
                account_id=account.id,
                type=parsed["type"],
                amount=Decimal(str(parsed["amount"])),
                currency=parsed.get("currency") or base_currency(),
                category=parsed.get("category"),
                description=parsed.get("description"),
                occurred_at=occurred,
            )
            session.add(txn)
        
        await session.commit()
        await callback.answer(fmsg("confirm_recorded"))
    return True
