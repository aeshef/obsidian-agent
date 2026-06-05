"""FSM states for finance transaction wizard and NLU confirmation."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddTxnState(StatesGroup):
    type = State()
    amount = State()
    category = State()
    account = State()
    confirm = State()


class ConfirmTransactionsState(StatesGroup):
    transactions = State()
