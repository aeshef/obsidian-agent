import asyncio

import pytest

from bot.services import categories
from bot.services.transactions import core


@pytest.fixture
def category_config(tmp_path, monkeypatch):
    monkeypatch.setattr(categories, "_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(categories, "agent_locale", lambda: "en")
    monkeypatch.setattr(categories, "get_nlu_config", lambda: {
        "broker_categories": {"topup": "Broker deposit", "withdraw": "Broker withdrawal", "fee": "Broker fee"}
    })
    (tmp_path / "categories_mvp.en.yaml.example").write_text('- Food\n')
    (tmp_path / "income_categories.en.yaml.example").write_text('- Salary\n')
    return tmp_path


def test_broker_labels_available_in_correct_transaction_types(category_config):
    assert categories.load_categories() == ["Food", "Broker deposit", "Broker fee"]
    assert categories.load_categories("income") == ["Salary", "Broker withdrawal"]


def test_personal_list_wins_and_broker_labels_not_duplicated(category_config):
    (category_config / "categories_mvp.yaml").write_text('- Custom\n- Broker deposit\n')
    assert categories.load_categories() == ["Custom", "Broker deposit", "Broker fee"]
    (category_config / "categories_mvp.en.yaml").write_text('- Locale custom\n')
    assert categories.load_categories()[0] == "Locale custom"


def test_topup_requires_account_not_category_and_does_not_write(category_config, monkeypatch):
    def forbidden_db():
        raise AssertionError("No transaction or account writes allowed")
    monkeypatch.setattr(core, "AsyncSessionLocal", forbidden_db)
    parsed = {"type": "expense", "amount": 123, "category": "Broker deposit", "account": None}
    missing = asyncio.run(core.get_missing_fields(parsed, 1))
    assert missing == {"account": True}
    assert parsed["_found_category_name"] == "Broker deposit"
