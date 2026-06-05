"""domain_messages.ru loads legacy domain_messages.yaml when .ru.yaml is absent."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared import domain_messages as dm


@pytest.fixture(autouse=True)
def _clear_domain_cache():
    dm.clear_domain_messages_cache()
    yield
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
