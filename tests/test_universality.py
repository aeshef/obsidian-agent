"""Universality helpers: LLM env aliases, health_snapshots, currency, CSV broker."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from shared.capabilities.profile import CONNECTOR_APPLE_HEALTH, profile_from_document
from shared.constants import deepseek_base_url, deepseek_model, llm_api_key
from shared.finance.currency import base_currency, is_base_currency
from shared.setup.env_secrets import is_placeholder_secret, resolve_llm_key


def test_llm_env_aliases(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_TOKEN", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-" + "x" * 32)
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    assert llm_api_key() == "sk-" + "x" * 32
    assert deepseek_base_url() == "https://openrouter.ai/api/v1"
    assert deepseek_model() == "openai/gpt-4o-mini"
    assert resolve_llm_key().startswith("sk-")


def test_llm_legacy_deepseek_still_works(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "y" * 32)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    assert llm_api_key() == "sk-" + "y" * 32
    assert deepseek_base_url().endswith("deepseek.com/v1")


def test_health_snapshots_yaml_alias():
    doc = {
        "modules": {"planning": True, "finance": False, "knowledge": False},
        "connectors": {"health_snapshots": True},
        "sync": {"profile": "minimal"},
    }
    prof = profile_from_document(doc)
    assert prof.connector(CONNECTOR_APPLE_HEALTH) is True


def test_base_currency_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BASE_CURRENCY", "usd")
    assert base_currency() == "USD"
    assert is_base_currency("USD")
    assert not is_base_currency("EUR")
    monkeypatch.setenv("BASE_CURRENCY", "RUB")
    assert is_base_currency("RUR")


def test_placeholder_accepts_llm_key_name():
    assert is_placeholder_secret("LLM_API_KEY", "sk-...")
    assert is_placeholder_secret("LLM_API_KEY", "")
    assert not is_placeholder_secret("LLM_API_KEY", "sk-" + "a" * 32)
    assert not is_placeholder_secret("LLM_API_KEY", "local-vllm-token-ok")


def test_csv_broker_provider_listed():
    from finance_bot.bot.services.broker_providers import supported_broker_providers

    assert "csv" in supported_broker_providers()


def test_health_sample_parses():
    from planning_bot.services.iphone_health_fields import extract_raw_fields

    sample = Path("docs/connectors/health/samples/evening_checkin.txt")
    assert sample.is_file()
    fields = extract_raw_fields(sample.read_text(encoding="utf-8"))
    assert fields.get("source") == "sample_evening"
    assert "weight_kg" in fields or "steps" in fields


def test_csv_balance_parse():
    from finance_bot.bot.services.csv_broker_sync import _parse_balance

    assert _parse_balance("1 000,50") == Decimal("1000.50")
    assert _parse_balance("42") == Decimal("42")
