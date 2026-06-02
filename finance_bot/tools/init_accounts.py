#!/usr/bin/env python3
"""Initialize accounts from config/initial_accounts.yaml."""

import asyncio
import os
import sys
from pathlib import Path
import yaml
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import declarative_base
from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

[REDACTED]

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="RUB")
    reminder_time: Mapped[str] = mapped_column(String(8), default="21:00")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(24), default="wallet")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    is_external_balance: Mapped[bool] = mapped_column(Boolean, default=False)
    external_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


from shared.domain_messages import dmsg


async def init_accounts_from_config():
    """Load accounts from initial_accounts.yaml into the database."""
    os.chdir(PROJECT_ROOT)

    config_path = PROJECT_ROOT / "config" / "initial_accounts.yaml"

    if not config_path.exists():
        print(dmsg("finance_scripts", "init_config_missing", path=config_path))
        print(dmsg("finance_scripts", "init_config_hint"))
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    telegram_id = config.get("telegram_id")
    if not telegram_id:
        print(dmsg("finance_scripts", "init_no_telegram_id"))
        return

    accounts_config = config.get("accounts", [])
    if not accounts_config:
        print(dmsg("finance_scripts", "init_no_accounts"))
        return

    print(dmsg("finance_scripts", "init_accounts_found", count=len(accounts_config)))
    print(f"Telegram ID: {telegram_id}\n")

    database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./finance.db")
    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()

        if not user:
            print(dmsg("finance_scripts", "init_user_missing", telegram_id=telegram_id))
            print(dmsg("finance_scripts", "init_user_hint"))
            return

        created_count = 0
        updated_count = 0

        for acc_config in accounts_config:
            name = acc_config.get("name", "").strip()
            balance = acc_config.get("balance", 0)
            currency = acc_config.get("currency", "RUB").upper()
            acc_type = acc_config.get("type", "wallet")

            if not name:
                print(dmsg("finance_scripts", "init_skip_no_name"))
                continue

            existing = (
                await session.execute(
                    select(Account).where(Account.user_id == user.id, Account.name == name)
                )
            ).scalar_one_or_none()

            balance_decimal = Decimal(str(balance))
            is_ext = acc_type in ("broker",)
            resolved_type = "broker_portfolio" if acc_type in ("broker",) else acc_type
            if existing:
                existing.external_balance = balance_decimal
                existing.currency = currency
                existing.type = resolved_type
                existing.is_external_balance = is_ext
                updated_count += 1
                print(
                    dmsg(
                        "finance_scripts",
                        "init_updated",
                        name=name,
                        balance=balance_decimal,
                        currency=currency,
                        external=is_ext,
                    )
                )
            else:
                account = Account(
                    user_id=user.id,
                    name=name,
                    type=resolved_type,
                    currency=currency,
                    is_external_balance=is_ext,
                    external_balance=balance_decimal,
                )
                session.add(account)
                created_count += 1
                print(
                    dmsg(
                        "finance_scripts",
                        "init_created",
                        name=name,
                        balance=balance_decimal,
                        currency=currency,
                    )
                )

        await session.commit()

        print(dmsg("finance_scripts", "init_done"))
        print(dmsg("finance_scripts", "init_created_count", count=created_count))
        print(dmsg("finance_scripts", "init_updated_count", count=updated_count))
        print(dmsg("finance_scripts", "init_total", count=created_count + updated_count))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_accounts_from_config())
