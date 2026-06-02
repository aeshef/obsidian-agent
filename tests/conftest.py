"""Shared fixtures for agent platform tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINANCE_BOT = ROOT / "finance_bot"
FIXTURE_VAULT = Path(__file__).parent / "fixtures" / "vault"


os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("TELEGRAM_FINANCE_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-for-pytest")

for p in (str(FINANCE_BOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


import pytest


@pytest.fixture(autouse=True)
def _knowledge_subdir_for_tests(monkeypatch):
    """Stable rel_path prefix in knowledge tests (matches legacy fixture paths)."""
    monkeypatch.setenv("VAULT_REL_KNOWLEDGE", "700_База_Данных")
    from shared.agent.platform_config import load_platform_config

    load_platform_config.cache_clear()


def knowledge_rel(*parts: str) -> str:
    from shared.vault_layout import knowledge_subdir

    base = knowledge_subdir()
    tail = "/".join(p.strip("/") for p in parts if p)
    return f"{base}/{tail}" if tail else base


@pytest.fixture(scope="session")
async def finance_db():
    """SQLite schema for finance_bot tests that touch AsyncSessionLocal."""
    from bot.db import Base, get_engine
    import bot.models  # noqa: F401 — register tables on Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
