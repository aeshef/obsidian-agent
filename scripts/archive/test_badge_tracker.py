#!/usr/bin/env python3
"""Юнит-тесты логики бейджа (без Telegram)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.services.badge_tracker import BadgeTracker  # noqa: E402


class TestBadgeTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = BadgeTracker(
            {
                "daily_limit_rub": 1000,
                "ndfl_rate": 0.13,
                "extra_non_working_days": [],
                "extra_working_days": [],
            }
        )

    def test_working_day_weekday(self) -> None:
        self.assertTrue(self.tracker.is_working_day(date(2026, 4, 22)))  # Wed
        self.assertFalse(self.tracker.is_working_day(date(2026, 4, 19)))  # Sun

    def test_day_metrics_burn_and_ndfl(self) -> None:
        d = date(2026, 4, 22)
        ds = self.tracker._day_metrics(d, Decimal("300"))
        self.assertEqual(ds.burned, Decimal("700"))
        self.assertEqual(ds.ndfl_cost, Decimal("39.00"))

    def test_day_metrics_over_limit(self) -> None:
        d = date(2026, 4, 22)
        ds = self.tracker._day_metrics(d, Decimal("1200"))
        self.assertEqual(ds.over_limit, Decimal("200"))
        self.assertEqual(ds.ndfl_cost, Decimal("130.00"))

    def test_month_stats_sync(self) -> None:
        import sqlite3

        from bot.db import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            from bot.models import Account, User

            user = User(telegram_id=999, chat_id=999)
            session.add(user)
            session.flush()
            acc = Account(user_id=user.id, name="Meal Badge", type="badge", currency="RUB")
            session.add(acc)
            session.flush()
            from bot.models import Transaction
            from datetime import datetime

            session.add(
                Transaction(
                    user_id=user.id,
                    account_id=acc.id,
                    type="expense",
                    amount=Decimal("450"),
                    currency="RUB",
                    category="Еда/Бейдж",
                    occurred_at=datetime(2026, 4, 22, 12, 0),
                )
            )
            session.commit()
            user_id = user.id
            session.close()

            conn = sqlite3.connect(db_path)
            m = self.tracker.month_stats_sync(conn, user_id, 2026, 4)
            conn.close()
            self.assertIsNotNone(m)
            assert m is not None
            self.assertGreater(m.total_spent, 0)
            self.assertGreaterEqual(m.working_days, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
