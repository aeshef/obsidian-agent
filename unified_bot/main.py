"""Entry point: single Telegram bot hosting all domains."""
from __future__ import annotations

import asyncio
from pathlib import Path

from shared.setup.load_env import load_repo_env
from unified_bot.host.bootstrap import run_host_bot


def main() -> None:
    load_repo_env(Path(__file__).resolve().parents[1])
    asyncio.run(run_host_bot())


if __name__ == "__main__":
    main()
