#!/usr/bin/env python3
import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

# Ensure project root on sys.path when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from sqlalchemy import select

from bot.db import AsyncSessionLocal
from bot.models import User, Account, Transaction


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.replace(" ", "").replace(",", ".")
        return Decimal(cleaned)
    raise ValueError(f"Unsupported number type: {type(value)}")


async def _get_single_user_id() -> int:
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        if not users:
            raise RuntimeError("No users found. Run the bot and press /start once to create a user.")
        if len(users) > 1:
            users.sort(key=lambda u: u.id, reverse=True)
        return users[0].id


async def _upsert_account(session, user_id: int, name: str, acc_type: str, currency: str,
                          is_external: bool = False, external_balance: Optional[Decimal] = None) -> Account:
    acc = (
        await session.execute(
            select(Account).where(Account.user_id == user_id, Account.name == name)
        )
    ).scalar_one_or_none()
    if acc is None:
        acc = Account(
            user_id=user_id,
            name=name,
            type=acc_type,
            currency=currency,
            is_external_balance=is_external,
            external_balance=external_balance,
        )
        session.add(acc)
        await session.flush()
    else:
        acc.type = acc_type
        acc.currency = currency
        acc.is_external_balance = is_external
        acc.external_balance = external_balance
    return acc


async def _create_opening_income(session, user_id: int, account: Account, amount: Decimal, when: datetime) -> None:
    if amount == Decimal("0"):
        return
    txn = Transaction(
        user_id=user_id,
        account_id=account.id,
        type="income",
        amount=amount,
        currency=account.currency,
        category="Opening Balance",
        description=f"Opening balance as of {when.date().isoformat()}",
        occurred_at=when,
    )
    session.add(txn)


async def import_from_yaml(yaml_path: Path) -> None:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    user_id = await _get_single_user_id()

    async with AsyncSessionLocal() as session:
        # Accounts (fiat and generic)
        seen_names: set[str] = set()
        for item in data.get("accounts", []):
            name = str(item.get("name", "")).strip()
            acc_type = str(item.get("type", "wallet")).strip()
            currency = str(item.get("currency", "RUB")).strip()
            balance = item.get("balance", 0)
            ext_balance = item.get("external_balance")
            balance_as_of = item.get("balance_as_of") or datetime.utcnow().date().isoformat()

            base_name = name
            suffix = 1
            while name in seen_names:
                suffix += 1
                name = f"{base_name} #{suffix}"
            seen_names.add(name)

            is_external = False
            external_value: Optional[Decimal] = None
            if acc_type in ("broker_portfolio", "receivable", "liability_payable"):
                is_external = True
                if ext_balance is not None:
                    external_value = _to_decimal(ext_balance)
                else:
                    external_value = _to_decimal(balance)

            acc = await _upsert_account(
                session,
                user_id=user_id,
                name=name,
                acc_type=acc_type,
                currency=currency,
                is_external=is_external,
                external_balance=external_value,
            )

            if not is_external:
                amt = _to_decimal(balance)
                when_dt = datetime.fromisoformat(balance_as_of)
                await _create_opening_income(session, user_id, acc, amt, when_dt)

        # Debts
        debts = data.get("debts", {}) or {}
        for rec in debts.get("receivables", []) or []:
            cp = str(rec.get("counterparty", "")).strip()
            amount = _to_decimal(rec.get("amount", 0))
            currency = str(rec.get("currency", "RUB")).strip()
            acc_name = f"receivable:{cp}"
            await _upsert_account(
                session,
                user_id=user_id,
                name=acc_name,
                acc_type="receivable",
                currency=currency,
                is_external=True,
                external_balance=amount,
            )

        for pay in debts.get("payables", []) or []:
            cp = str(pay.get("counterparty", "")).strip()
            amount = _to_decimal(pay.get("amount", 0))
            currency = str(pay.get("currency", "RUB")).strip()
            acc_name = f"liability_payable:{cp}"
            await _upsert_account(
                session,
                user_id=user_id,
                name=acc_name,
                acc_type="liability_payable",
                currency=currency,
                is_external=True,
                external_balance=amount,
            )

        # Crypto assets -> create per-asset external accounts: "<Wallet>:<SYMBOL>"
        crypto = data.get("crypto", {}) or {}
        for w in crypto.get("wallets", []) or []:
            wname = str(w.get("name", "")).strip()
            for a in w.get("assets", []) or []:
                symbol = str(a.get("symbol", "")).strip().upper()
                if not symbol:
                    continue
                try:
                    amount = _to_decimal(a.get("amount", 0))
                except Exception:
                    continue
                acc_name = f"{wname}:{symbol}"
                await _upsert_account(
                    session,
                    user_id=user_id,
                    name=acc_name,
                    acc_type="crypto",
                    currency=symbol,
                    is_external=True,
                    external_balance=amount,
                )

        await session.commit()


async def amain(path: str) -> None:
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")
    await import_from_yaml(yaml_path)
    print("Initialization complete.")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Initialize finance DB from YAML")
    parser.add_argument("--file", default=str(Path("data/init.yaml")))
    args = parser.parse_args()

    asyncio.run(amain(args.file))


if __name__ == "__main__":
    main()
