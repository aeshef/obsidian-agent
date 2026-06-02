"""NLU config и looks_like_transaction (без keyword-gate)."""
from __future__ import annotations

from bot.services.transactions.core import looks_like_transaction, infer_account_type


def test_looks_like_transaction_min_length():
    assert looks_like_transaction("привет как дела") is True
    assert looks_like_transaction("  ") is False
    assert looks_like_transaction("ab") is False


def test_infer_account_type_from_config_hints():
    assert infer_account_type("Тинькофф карта") == "card"
    assert infer_account_type("Наличные") == "wallet"


def test_nlu_config_has_required_keys():
    from bot.config_loader import get_nlu_config, nlu_menu_buttons

    cfg = get_nlu_config()
    for key in (
        "broker_categories",
        "exact_commands",
        "min_text_length",
        "account_type_card_hints",
    ):
        assert key in cfg
    # menu_buttons optional in nlu_config.yaml — labels come from messages.ru.yaml
    assert len(nlu_menu_buttons(cfg)) >= 1
