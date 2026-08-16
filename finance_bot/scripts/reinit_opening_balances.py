#!/usr/bin/env python3
"""Reinit account opening balances (external_balance) to match real-life targets.

Keeps all transactions. Default is dry-run.

  python scripts/reinit_opening_balances.py --db /path/finance.db
  python scripts/reinit_opening_balances.py --db /path/finance.db --apply --backup-dir /tmp
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

_FB_ROOT = Path(__file__).resolve().parents[1]
_REPO = _FB_ROOT.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_FB_ROOT) not in sys.path:
    sys.path.insert(0, str(_FB_ROOT))

from bot.services.reinit_opening_balances import (  # noqa: E402
    apply_reinit_plan,
    build_reinit_plan,
    count_transactions,
    default_targets_2026_08_09,
    open_db,
    verify_plan_against_db,
)


def _backup(db: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"finance.db.bak_reinit_{stamp}"
    shutil.copy2(db, dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, required=True, help="Path to finance.db")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default: dry-run only)",
    )
    ap.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for DB backup before --apply (required with --apply)",
    )
    args = ap.parse_args()
    db = args.db.expanduser().resolve()
    if not db.is_file():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1
    if args.apply and args.backup_dir is None:
        print("--apply requires --backup-dir", file=sys.stderr)
        return 2

    targets = default_targets_2026_08_09()
    conn = open_db(db)
    try:
        txn_before = count_transactions(conn)
        plan = build_reinit_plan(conn, targets)
        print(f"db={db}")
        print(f"transactions={txn_before} (must stay unchanged)")
        print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
        print("-" * 72)
        for row in plan:
            print(
                f"{row.name}: current={row.old_current} → target={row.target} | "
                f"ext {row.old_external} → {row.new_external} "
                f"(Δext={row.delta_external}, txn_net={row.txn_net}, "
                f"external_only={row.is_external_balance})"
            )
        print("-" * 72)

        if not args.apply:
            print("dry-run ok; re-run with --apply --backup-dir DIR to write")
            return 0

        bak = _backup(db, args.backup_dir.expanduser().resolve())
        print(f"backup → {bak}")
        apply_reinit_plan(conn, plan, dry_run=False)
        txn_after = count_transactions(conn)
        if txn_after != txn_before:
            print(
                f"FATAL: transaction count changed {txn_before} → {txn_after}",
                file=sys.stderr,
            )
            return 3
        verified = verify_plan_against_db(conn, plan)
        bad = []
        for row in plan:
            got = verified[row.name]
            if got != row.target:
                bad.append((row.name, row.target, got))
        if bad:
            print("FATAL: post-apply balance mismatch:", file=sys.stderr)
            for name, want, got in bad:
                print(f"  {name}: want={want} got={got}", file=sys.stderr)
            return 4
        print("apply ok; all targets match; txn count unchanged")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
