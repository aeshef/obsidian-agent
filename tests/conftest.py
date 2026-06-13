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
os.environ.setdefault("AGENT_LOCALE", "en")

for p in (str(FINANCE_BOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


import pytest


@pytest.fixture(autouse=True)
def _clear_capability_caches():
    """Env overrides in one test must not leak via get_capabilities() lru_cache."""
    from shared.capabilities.profile import clear_capabilities_cache
    from shared.capabilities.ui_bindings import clear_ui_bindings_cache
    from shared.telegram.host.domain_routing import clear_domain_routing_cache
    from shared.telegram.host.menu_detection import clear_menu_detection_cache

    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_domain_routing_cache()
    clear_menu_detection_cache()
    try:
        from planning_bot.app.menu_labels import clear_menu_label_cache

        clear_menu_label_cache()
    except Exception:
        pass
    yield
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_domain_routing_cache()
    clear_menu_detection_cache()
    try:
        from planning_bot.app.menu_labels import clear_menu_label_cache

        clear_menu_label_cache()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _pytest_agent_locale_ru(monkeypatch):
    """RU vault fixtures (100_Задачи) + legacy assertions; locale parity has dedicated tests."""
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    from shared import i18n
    from shared import vault_paths_config as vp
    from shared import domain_messages as dm

    i18n.clear_messages_cache()
    vp.vault_paths_config.cache_clear()
    dm.clear_domain_messages_cache()
    yield
    i18n.clear_messages_cache()
    vp.vault_paths_config.cache_clear()
    dm.clear_domain_messages_cache()


@pytest.fixture(autouse=True)
def _knowledge_subdir_for_tests(monkeypatch):
    """Stable rel_path prefix in knowledge tests (matches legacy fixture paths)."""
    monkeypatch.setenv("VAULT_REL_KNOWLEDGE", "700_База_Данных")
    from shared.agent.platform_config import load_platform_config

    load_platform_config.cache_clear()


@pytest.fixture(autouse=True)
def _domain_messages_merge_example(monkeypatch):
    """Tests see domain_messages en+ru examples merged under local overrides."""
    from functools import lru_cache

    from shared import domain_messages as dm
    from shared.yaml_config import deep_merge, load_yaml

    cfg = ROOT / "config"
    ru = load_yaml(cfg / "domain_messages.ru.yaml.example", default={})
    en = load_yaml(cfg / "domain_messages.en.yaml.example", default={})
    merged = deep_merge(ru, en)
    local_path = cfg / "domain_messages.en.yaml"
    if not local_path.is_file():
        local_path = cfg / "domain_messages.yaml"
    local = load_yaml(local_path, default={}) if local_path.is_file() else {}
    if local:
        merged = deep_merge(merged, local)

    @lru_cache(maxsize=2)
    def _merged_domain(_locale: str) -> dict:
        if str(_locale).startswith("en"):
            return deep_merge(ru, en)
        return ru

    monkeypatch.setattr(dm, "_domain", _merged_domain)
    dm.clear_domain_messages_cache()
    try:
        from planning_bot.services import action_log_parser as alp
        from planning_bot.services import action_logger as al
        from planning_bot.services.action_log_format import _glued_type_re, _loose_json_block_re

        alp._log_entry_pattern.cache_clear()
        al._log_entry_re.cache_clear()
        al._legacy_log_entry_re.cache_clear()
        _glued_type_re.cache_clear()
        _loose_json_block_re.cache_clear()
    except Exception:
        pass
    yield
    dm.clear_domain_messages_cache()


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
