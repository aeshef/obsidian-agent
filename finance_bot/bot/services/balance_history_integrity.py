"""Preserve unassignable legacy balances in an explicit archive, without guessing account identity."""
from __future__ import annotations
import sqlite3


def archive_orphaned_snapshots(db: sqlite3.Connection) -> int:
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''CREATE TABLE IF NOT EXISTS archived_account_balance_snapshots (
            archive_id INTEGER PRIMARY KEY,
            original_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            balance NUMERIC(18,2) NOT NULL,
            reason TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(original_id, account_id, snapshot_date, balance)
        )''')
        rows = db.execute('''SELECT s.id,s.account_id,s.snapshot_date,s.balance
            FROM account_balance_snapshots s LEFT JOIN accounts a ON a.id=s.account_id
            WHERE a.id IS NULL''').fetchall()
        db.executemany('''INSERT OR IGNORE INTO archived_account_balance_snapshots
            (original_id,account_id,snapshot_date,balance,reason) VALUES(?,?,?,?,'missing_legacy_account')''', rows)
        for row in rows:
            assert db.execute('''SELECT 1 FROM archived_account_balance_snapshots
                WHERE original_id=? AND account_id=? AND snapshot_date=? AND balance=?''', row).fetchone()
        db.executemany('DELETE FROM account_balance_snapshots WHERE id=?', [(row[0],) for row in rows])
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise sqlite3.IntegrityError('Unresolved foreign key violation; archive rolled back')
    return len(rows)
