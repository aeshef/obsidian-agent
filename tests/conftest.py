"""Shared fixtures for agent platform tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINANCE_BOT = ROOT / "finance_bot"
FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"

# До любого import bot.* — иначе pydantic Settings валится на токенах
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("TELEGRAM_FINANCE_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-for-pytest")

for p in (str(FINANCE_BOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
