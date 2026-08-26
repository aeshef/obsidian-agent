"""domain_messages.ru loads legacy domain_messages.yaml when .ru.yaml is absent."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared import domain_messages as dm


@pytest.fixture(autouse=True)
def _clear_domain_cache():
    original = dm._REPO_CONFIG
    dm.clear_domain_messages_cache()
    yield
    dm._REPO_CONFIG = original
    dm.clear_domain_messages_cache()


def test_ru_falls_back_to_legacy_domain_messages_yaml(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "domain_messages.ru.yaml.example").write_text(
        "planning:\n  probe_key: example\n",
        encoding="utf-8",
    )
    (cfg / "domain_messages.yaml").write_text(
        "planning:\n  probe_key: legacy\n",
        encoding="utf-8",
    )
    dm._REPO_CONFIG = cfg
    monkeypatch.setattr("shared.domain_messages.agent_locale", lambda: "ru")
    dm.clear_domain_messages_cache()

    assert dm._ru_domain().get("planning", {}).get("probe_key") == "legacy"


def test_ru_fills_missing_keys_from_example(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "domain_messages.ru.yaml.example").write_text(
        "planning:\n  probe_key: example\n  new_key: from_example\n",
        encoding="utf-8",
    )
    (cfg / "domain_messages.ru.yaml").write_text(
        "planning:\n  probe_key: local\n",
        encoding="utf-8",
    )
    dm._REPO_CONFIG = cfg
    monkeypatch.setattr("shared.domain_messages.agent_locale", lambda: "ru")
    dm.clear_domain_messages_cache()

    planning = dm._ru_domain().get("planning") or {}
    assert planning.get("probe_key") == "local"
    assert planning.get("new_key") == "from_example"


def test_real_ru_catalog_fills_goals_mapping_review_title():
    title = (dm._ru_domain().get("planning") or {}).get("goals_mapping_review_title")
    assert title
    assert "Маппинг" in str(title)
