"""Entry point: single Telegram bot hosting all domains."""
from __future__ import annotations

import asyncio

from shared.telegram.host.bootstrap import run_host_bot


def main() -> None:
    asyncio.run(run_host_bot())


if __name__ == "__main__":
    main()
