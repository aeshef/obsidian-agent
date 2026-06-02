#!/usr/bin/env python3
"""Delete all transactions and reset non-external account balances."""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.db import AsyncSessionLocal
from bot.models import Transaction, Account
from shared.domain_messages import dmsg


async def reset_all_transactions():
    """Delete all transactions."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Transaction))
        transactions = result.scalars().all()
        count = len(transactions)

        for txn in transactions:
            await session.delete(txn)

        await session.commit()
        print(dmsg("finance_scripts", "reset_tx_deleted", count=count))


async def reset_account_balances():
    """Reset balances for non-external accounts."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Account).where(Account.is_external_balance == False)
        )
        accounts = result.scalars().all()

        for acc in accounts:
            acc.external_balance = None

        await session.commit()
        print(dmsg("finance_scripts", "reset_balances", count=len(accounts)))


async def main():
    print(dmsg("finance_scripts", "reset_start"))

    await reset_all_transactions()
    await reset_account_balances()

    print(dmsg("finance_scripts", "reset_done"))
    print(dmsg("finance_scripts", "reset_external_hint"))


if __name__ == "__main__":
    asyncio.run(main())
