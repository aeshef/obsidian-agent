"""Finance transaction handlers package."""
from __future__ import annotations

from aiogram import Router

from bot.handlers.transactions.balance import _render_balance, router as balance_router
from bot.handlers.transactions.confirmation import show_transaction_confirmation
from bot.handlers.transactions.nlu import (
    handle_natural_language,
    process_transactions,
    router as nlu_router,
)
from bot.handlers.transactions.states import AddTxnState, ConfirmTransactionsState
from bot.handlers.transactions.wizard import router as wizard_router
from bot.services.transactions.core import (
    get_missing_fields,
    get_or_create_account,
    handle_broker_withdraw,
    parse_occurred_at,
)

router = Router(name="finance_transactions")
router.include_router(wizard_router)
router.include_router(balance_router)
router.include_router(nlu_router)

# Legacy aliases (transactions_confirm.py, financial_query.py)
_parse_occurred_at = parse_occurred_at
_get_missing_fields = get_missing_fields
_get_or_create_account = get_or_create_account
_handle_broker_withdraw = handle_broker_withdraw
_process_transactions = process_transactions

__all__ = [
    "router",
    "_render_balance",
    "show_transaction_confirmation",
    "ConfirmTransactionsState",
    "AddTxnState",
    "process_transactions",
    "handle_natural_language",
    "_parse_occurred_at",
    "_get_missing_fields",
    "_get_or_create_account",
    "_handle_broker_withdraw",
    "_process_transactions",
]
