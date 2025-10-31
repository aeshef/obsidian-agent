#!/usr/bin/env python3
import argparse
import json
import sys
import traceback
from pathlib import Path

# Ensure project root on sys.path when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import get_settings


def main():
    parser = argparse.ArgumentParser(description="Tinkoff Invest debug tester")
    parser.add_argument("--token", help="Tinkoff API token (overrides .env)", default=None)
    args = parser.parse_args()

    settings = get_settings()
    token = args.token or (settings.TINKOFF_API_TOKEN or "")
    if not token:
        print("No token provided. Set TINKOFF_API_TOKEN in .env or pass --token.", file=sys.stderr)
        sys.exit(2)

    try:
        from tinkoff_sync import fetch_tinkoff_summary  # type: ignore
    except Exception as e:
        print(f"Import error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

    try:
        data = fetch_tinkoff_summary(token)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(0)
    except Exception as e:
        print(f"Runtime error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
