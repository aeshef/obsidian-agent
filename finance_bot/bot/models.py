from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from typing import List
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    reminder_time: Mapped[str] = mapped_column(String(8), default="21:00")  # HH:MM
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    accounts: Mapped[List[Account]] = relationship(back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[List[Transaction]] = relationship(back_populates="user", cascade="all, delete-orphan")
    planned_expenses: Mapped[List["PlannedExpense"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "external_ref", name="uq_accounts_user_external_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    # Stable external account key (e.g. T-Invest account id). Upsert by (user_id, external_ref).
    external_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(24), default="wallet")  # wallet/card/broker/crypto/other
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    is_external_balance: Mapped[bool] = mapped_column(Boolean, default=False)
    external_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="accounts")
    transactions: Mapped[List[Transaction]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(8))  # expense | income
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="transactions")
    account: Mapped[Account] = relationship(back_populates="transactions")


class AccountBalanceSnapshot(Base):
    """End-of-day account balance snapshot (broker: written on each sync)."""

    __tablename__ = "account_balance_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "snapshot_date", name="uq_account_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class PlannedExpense(Base):
    """Planned expense (savings goal or upcoming spend)."""

    __tablename__ = "planned_expenses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active")  # active | done | cancelled | expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="planned_expenses")

