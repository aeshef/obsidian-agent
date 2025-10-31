#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# ensure project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="Tinkoff SDK tester (accounts + portfolio)")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    try:
        from tinkoff.invest import Client
    except Exception as e:
        print("tinkoff-investments is not installed. Install: pip install tinkoff-investments", file=sys.stderr)
        sys.exit(2)

    if not args.token:
        try:
            from bot.config import get_settings
            token = get_settings().TINKOFF_API_TOKEN or ""
        except Exception:
            token = ""
    else:
        token = args.token

    if not token:
        print("Provide --token or set TINKOFF_API_TOKEN in .env", file=sys.stderr)
        sys.exit(2)

    from tinkoff.invest.schemas import PortfolioRequest
    try:
        with Client(token) as client:
            accs = client.users.get_accounts()
            print(f"Accounts: {[a.id for a in accs.accounts]}")
            for a in accs.accounts:
                try:
                    # currency left default; SDK handles it
                    p = client.operations.get_portfolio(account_id=a.id)
                    total = p.total_amount_portfolio
                    # Quotation has units and nano
                    val = (total.units or 0) + (total.nano or 0) / 1_000_000_000
                    print(f"Portfolio {a.id}: {val}")
                except Exception as e:
                    print(f"Portfolio error {a.id}: {e}")
    except Exception as e:
        print(f"SDK error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
