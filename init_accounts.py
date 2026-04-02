#!/usr/bin/env python3
"""Скрипт для инициализации счетов из конфига initial_accounts.yaml"""

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

# Устанавливаем DATABASE_URL до импорта моделей
[REDACTED]

# Создаем Base напрямую, чтобы не импортировать из bot.db
Base = declarative_base()


# Определяем модели напрямую (копия из bot/models.py)
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


async def init_accounts_from_config():
    """Инициализирует счета из конфига"""
    # Меняем рабочую директорию на директорию скрипта
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    config_path = script_dir / "config" / "initial_accounts.yaml"
    
    if not config_path.exists():
        print(f"❌ Конфиг не найден: {config_path}")
        print("💡 Создай файл config/initial_accounts.yaml (см. пример в README)")
        return
    
    # Загружаем конфиг
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    
    telegram_id = config.get("telegram_id")
    if not telegram_id:
        print("❌ В конфиге не указан telegram_id")
        return
    
    accounts_config = config.get("accounts", [])
    if not accounts_config:
        print("❌ В конфиге нет счетов (accounts)")
        return
    
    print(f"📋 Найдено счетов в конфиге: {len(accounts_config)}")
    print(f"👤 Telegram ID: {telegram_id}\n")
    
    # Создаем движок и сессию напрямую
    database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./finance.db")
    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Получаем пользователя
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()
        
        if not user:
            print(f"❌ Пользователь с telegram_id={telegram_id} не найден")
            print("💡 Сначала отправь /start боту, чтобы создать пользователя")
            return
        
        created_count = 0
        updated_count = 0
        
        for acc_config in accounts_config:
            name = acc_config.get("name", "").strip()
            balance = acc_config.get("balance", 0)
            currency = acc_config.get("currency", "RUB").upper()
            acc_type = acc_config.get("type", "wallet")
            
            if not name:
                print(f"⚠️ Пропущен счет без названия")
                continue
            
            # Проверяем, существует ли счет
            existing = (await session.execute(
                select(Account).where(Account.user_id == user.id, Account.name == name)
            )).scalar_one_or_none()
            
            balance_decimal = Decimal(str(balance))
            
            # Брокер — balance из API, is_external_balance=True
            # Карты и кошельки — is_external_balance=False, участвуют в переводах
            is_ext = acc_type in ("broker",)
            if existing:
                # Обновляем существующий счет
                existing.external_balance = balance_decimal
                existing.currency = currency
                existing.type = acc_type
                existing.is_external_balance = is_ext
                updated_count += 1
                print(f"✅ Обновлен: {name} = {balance_decimal:,.2f} {currency} (external={is_ext})")
            else:
                # Создаем новый счет
                account = Account(
                    user_id=user.id,
                    name=name,
                    type=acc_type,
                    currency=currency,
                    is_external_balance=is_ext,
                    external_balance=balance_decimal,
                )
                session.add(account)
                created_count += 1
                print(f"✅ Создан: {name} = {balance_decimal:,.2f} {currency}")
        
        await session.commit()
        
        print(f"\n✅ Готово!")
        print(f"   Создано счетов: {created_count}")
        print(f"   Обновлено счетов: {updated_count}")
        print(f"   Всего обработано: {created_count + updated_count}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_accounts_from_config())
