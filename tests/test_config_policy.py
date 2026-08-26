"""Config stem → loader policy registry (OSS audit F06)."""
from __future__ import annotations

import pytest

from shared.config_policy import CONFIG_STEM_LOADERS, load_by_policy, loader_kind_for_stem


def test_known_stems_have_loaders():
    assert loader_kind_for_stem("messages") == "catalog"
    assert loader_kind_for_stem("domain_messages") == "catalog"
    assert loader_kind_for_stem("kanban_schema") == "locale_merged"
    assert loader_kind_for_stem("ui_capabilities") == "merged"
    assert loader_kind_for_stem("platform") == "merged"


def test_unknown_stem_raises():
    with pytest.raises(KeyError, match="unknown config stem"):
        loader_kind_for_stem("not_a_real_stem")


def test_load_by_policy_messages(tmp_path, monkeypatch):
    ex = tmp_path / "messages.yaml.example"
    ex.write_text("host:\n  hi: from-example\n", encoding="utf-8")
    (tmp_path / "messages.yaml").write_text("host:\n  hi: local\n", encoding="utf-8")
    out = load_by_policy(str(tmp_path), "messages")
    assert out["host"]["hi"] == "local"


def test_registry_covers_catalog_and_locale():
    kinds = set(CONFIG_STEM_LOADERS.values())
    assert "catalog" in kinds
    assert "locale_merged" in kinds
    assert "merged" in kinds
