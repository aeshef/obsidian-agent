"""Legacy planning entrypoint — runs the unified host with a planning-first token."""
from __future__ import annotations

import asyncio
import os

from shared.telegram.host.bootstrap import run_host_bot


def _resolve_token() -> str:
    return (
        os.environ.get("TELEGRAM_PLANNING_BOT_TOKEN")
        or os.environ.get("TELEGRAM_UNIFIED_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()


def main() -> None:
    # Host still loads all enabled capability modules; token may be domain-specific.
    os.environ.setdefault("DEPLOY_MODE", "single")
    token = _resolve_token()
    asyncio.run(run_host_bot(token=token or None, token_env="TELEGRAM_PLANNING_BOT_TOKEN"))


if __name__ == "__main__":
    main()
