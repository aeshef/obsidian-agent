#!/usr/bin/env python3
"""Скрипт для очистки всех транзакций и сброса балансов счетов"""

import asyncio
from bot.db import AsyncSessionLocal
from bot.models import Transaction, Account
from sqlalchemy import select, update
from decimal import Decimal


async def reset_all_transactions():
    """Удаляет все транзакции"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Transaction))
        transactions = result.scalars().all()
        count = len(transactions)
        
        for txn in transactions:
            await session.delete(txn)
        
        await session.commit()
        print(f"✅ Удалено транзакций: {count}")


async def reset_account_balances():
    """Сбрасывает балансы всех счетов (кроме внешних)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Account).where(Account.is_external_balance == False)
        )
        accounts = result.scalars().all()
        
        for acc in accounts:
            acc.external_balance = None
        
        await session.commit()
        print(f"✅ Сброшены балансы для {len(accounts)} счетов")


async def main():
    print("🔄 Начинаю очистку данных...")
    
    await reset_all_transactions()
    await reset_account_balances()
    
    print("\n✅ Готово! Все транзакции удалены, балансы сброшены.")
    print("💡 Внешние балансы (брокерские счета) не изменены.")


if __name__ == "__main__":
    asyncio.run(main())
