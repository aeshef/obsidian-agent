#!/usr/bin/env python3
"""CLI: build finance dashboard markdown from finance.db.

Logic lives in ``bot.services.dashboard.build`` (keep this file thin).
"""
from __future__ import annotations

import sys
from pathlib import Path

from shared.bootstrap import setup_bot

setup_bot("finance_bot")

from bot.services.dashboard.build import build_arg_parser, log_dashboard, run_build  # noqa: E402


def main() -> int:
    args = build_arg_parser().parse_args()
    log_file = Path(__file__).resolve().parent.parent / "logs" / "build_finance_dashboard.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_build(args)
        return 0
    except Exception as e:
        log_dashboard(f"ERROR: {e}", log_file)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
