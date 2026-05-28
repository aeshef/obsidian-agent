#!/usr/bin/env python3
"""
Однократная чистка дублей broker_portfolio (старые «Тинькофф Брокер 4985» и т.п.).

Запуск на сервере после деплоя и broker sync:
  cd ~/bots/finance_bot && venv/bin/python tools/cleanup_broker_portfolio_accounts.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


async def main() -> None:
    from sqlalchemy import select

    from bot.db import AsyncSessionLocal, Base, _engine
    from bot import models  # noqa: F401
    from bot.models import Account, Transaction
    from bot.schema_migrate import run_schema_migrations
    from bot.broker_portfolio import (
        BROKER_PORTFOLIO_ACCOUNT_TYPE,
        is_legacy_suffixed_portfolio_name,
        legacy_orphan_portfolio_names,
    )
    from sqlalchemy import func

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(run_schema_migrations)

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Account).where(
                    Account.type == BROKER_PORTFOLIO_ACCOUNT_TYPE,
                    Account.is_external_balance.is_(True),
                )
            )
        ).scalars().all()
        print(f"broker_portfolio accounts: {len(rows)}")
        for a in rows:
            n_tx = (
                await session.execute(
                    select(func.count()).select_from(Transaction).where(Transaction.account_id == a.id)
                )
            ).scalar_one()
            print(
                f"  id={a.id} ref={a.external_ref!r} name={a.name!r} "
                f"balance={a.external_balance} tx={int(n_tx or 0)}"
            )

        removed = 0
        for a in list(rows):
            if a.external_ref:
                continue
            if not is_legacy_suffixed_portfolio_name(a.name) and a.name not in legacy_orphan_portfolio_names():
                continue
            n_tx = (
                await session.execute(
                    select(func.count()).select_from(Transaction).where(Transaction.account_id == a.id)
                )
            ).scalar_one()
            if int(n_tx or 0) > 0:
                print(f"SKIP id={a.id} (has transactions)")
                continue
            await session.delete(a)
            removed += 1
        await session.commit()
        print(f"Removed orphan legacy rows: {removed}")


if __name__ == "__main__":
    asyncio.run(main())
