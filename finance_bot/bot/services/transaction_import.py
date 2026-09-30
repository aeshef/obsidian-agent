"""Atomic, owner-scoped financial imports with duplicate checks and durable undo."""
import json
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from bot.models import Transaction, TransactionImport, Account
from bot.services.transactions import parse_occurred_at

FIELDS = ("account_id", "type", "amount", "currency", "category", "description", "occurred_at")


def snapshot(txn):
    return {key: str(Decimal(str(txn.amount)).quantize(Decimal("0.01"))) if key == "amount" else str(txn.occurred_at) if key == "occurred_at" else getattr(txn, key) for key in FIELDS}


async def resolve_row(session, user_id, row):
    if row.get("type") not in ("expense", "income"):
        raise ValueError("specialized_operation")
    try:
        amount = Decimal(str(row.get("amount")))
    except InvalidOperation as exc:
        raise ValueError("invalid_amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("invalid_amount")
    name = row.get("_found_account_name") or row.get("account")
    account = (await session.execute(select(Account).where(Account.user_id == user_id, Account.name == name))).scalar_one_or_none()
    if account is None or account.is_external_balance:
        raise ValueError("invalid_account")
    currency = row.get("currency") or account.currency
    if currency != account.currency or not row.get("category"):
        raise ValueError("invalid_currency_or_category")
    occurred = parse_occurred_at(row)
    return dict(user_id=user_id, account_id=account.id, type=row["type"], amount=amount,
                currency=currency, category=row.get("_found_category_name") or row["category"],
                description=row.get("description"), occurred_at=occurred)


async def duplicate_ids(session, values):
    start = datetime.combine(values["occurred_at"].date(), time.min)
    q = select(Transaction.id).where(Transaction.user_id == values["user_id"],
        Transaction.account_id == values["account_id"], Transaction.type == values["type"],
        Transaction.amount == values["amount"], Transaction.currency == values["currency"],
        Transaction.occurred_at >= start, Transaction.occurred_at < start+timedelta(days=1))
    return list((await session.execute(q)).scalars())


async def save_import(session, user_id, token, rows, *, allow_duplicates=False):
    receipt = await session.get(TransactionImport, token)
    if receipt:
        if receipt.user_id != user_id: raise ValueError("wrong_owner")
        return json.loads(receipt.payload)
    values = [await resolve_row(session, user_id, row) for row in rows]
    snapshots = []
    for value in values:
        if not allow_duplicates and await duplicate_ids(session, value):
            raise ValueError("duplicate_requires_review")
        txn = Transaction(**value); session.add(txn); await session.flush()
        snapshots.append({"id": txn.id, "values": snapshot(txn)})
    session.add(TransactionImport(id=token, user_id=user_id, payload=json.dumps(snapshots, ensure_ascii=False)))
    await session.flush()
    return snapshots


async def undo_import(session, user_id, token):
    receipt = (await session.execute(select(TransactionImport).where(TransactionImport.id == token,
                                TransactionImport.user_id == user_id))).scalar_one_or_none()
    if not receipt: raise ValueError("unknown_import")
    if receipt.undone: return 0
    rows = json.loads(receipt.payload); transactions = []
    for row in rows:
        txn = await session.get(Transaction, row["id"])
        if txn is None or txn.user_id != user_id or snapshot(txn) != row["values"]:
            raise ValueError("import_changed_since_save")
        transactions.append(txn)
    for txn in transactions: await session.delete(txn)
    receipt.undone = True
    return len(transactions)
