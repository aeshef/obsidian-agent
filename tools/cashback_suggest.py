#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime
import argparse

from bot.services.cashback_loader import iter_rules
from bot.services.cashback_engine import TxnContext, suggest_best_account


def main():
    parser = argparse.ArgumentParser(description="Cashback suggestion tool")
    parser.add_argument("--rules-dir", default=str(Path("cashback")), help="Directory with monthly YAML files")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--amount", type=float, required=True)
    parser.add_argument("--currency", default="RUB")
    parser.add_argument("--category", default=None)
    parser.add_argument("--merchant", default=None)
    parser.add_argument("--mcc", type=int, default=None)
    parser.add_argument("--accounts", nargs="+", required=True, help="Candidate account names")
    args = parser.parse_args()

    rules_dir = Path(args.rules_dir)
    files = sorted(rules_dir.glob("*.yaml"))
    rules = iter_rules(files)

    ctx = TxnContext(
        amount=args.amount,
        currency=args.currency,
        occurred_on=datetime.strptime(args.date, "%Y-%m-%d").date(),
        category=args.category,
        merchant=args.merchant,
        mcc=args.mcc,
    )

    est = suggest_best_account(ctx, rules, args.accounts)
    if est is None:
        print("No matching rules; choose any card or default policy.")
    else:
        print(f"Account: {est.account}\nRule: {est.rule_title} ({est.rule_id})\nEstimated cashback: {est.estimated_amount} {args.currency}\nReason: {est.reason}")


if __name__ == "__main__":
    main()

