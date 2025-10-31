#!/usr/bin/env python3
import asyncio
from argparse import ArgumentParser
from pathlib import Path
import sys

# ensure root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select, delete

from bot.db import AsyncSessionLocal
from bot.models import User, Account, Transaction


async def amain(name: str) -> None:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User))).scalars().first()
        if not user:
            print("No user found. Run /start once.")
            return
        acc = (
            await session.execute(select(Account).where(Account.user_id == user.id, Account.name == name))
        ).scalar_one_or_none()
        if not acc:
            print(f"Account not found: {name}")
            return
        await session.execute(delete(Transaction).where(Transaction.account_id == acc.id))
        await session.delete(acc)
        await session.commit()
        print(f"Deleted account: {name}")


def main():
    p = ArgumentParser(description="Delete account by name")
    p.add_argument("--name", required=True)
    args = p.parse_args()
    asyncio.run(amain(args.name))


if __name__ == "__main__":
    main()
