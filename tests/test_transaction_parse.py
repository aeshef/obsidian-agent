"""Integration: transaction keyword detection from nlu_config.yaml."""
from __future__ import annotations

from bot.config_loader import _config_cache, get_nlu_config
from bot.services.transactions.core import looks_like_transaction


def test_looks_like_transaction_positive():
    _config_cache.pop("nlu", None)
    cfg = get_nlu_config()
    sample_kw = cfg["transaction_keywords"][0]
    assert looks_like_transaction(f"сегодня {sample_kw} 500 на кофе") is True


def test_looks_like_transaction_negative():
    assert looks_like_transaction("привет как дела") is False
    assert looks_like_transaction("  ") is False


def test_nlu_config_has_required_keys():
    _config_cache.pop("nlu", None)
    cfg = get_nlu_config()
    for key in ("transaction_keywords", "exact_commands", "broker_categories", "menu_buttons"):
        assert key in cfg and cfg[key], f"missing or empty: {key}"
