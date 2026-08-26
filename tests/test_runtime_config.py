"""Runtime YAML loading (no example merge under local prod file)."""
from __future__ import annotations

import yaml

from shared.yaml_config import (
    clear_runtime_config_cache,
    load_catalog_config,
    load_locale_merged_config,
    load_merged_config,
    load_runtime_config,
)


def test_load_runtime_config_local_only(tmp_path):
    clear_runtime_config_cache()
    (tmp_path / "demo.yaml.example").write_text(
        yaml.dump({"a": 1, "nested": {"x": 1, "y": 2}}),
        encoding="utf-8",
    )
    (tmp_path / "demo.yaml").write_text(
        yaml.dump({"nested": {"x": 99}}),
        encoding="utf-8",
    )
    cfg_dir = str(tmp_path)
    runtime = load_runtime_config(cfg_dir, "demo")
    merged = load_merged_config(cfg_dir, "demo")
    catalog = load_catalog_config(cfg_dir, "demo")
    assert runtime == {"nested": {"x": 99}}
    assert merged["nested"]["x"] == 99
    assert merged["nested"]["y"] == 2
    assert catalog["nested"]["y"] == 2
    assert "y" not in runtime.get("nested", {})
    clear_runtime_config_cache()


def test_load_locale_merged_prefers_locale_example(tmp_path):
    clear_runtime_config_cache()
    (tmp_path / "kanban_schema.yaml.example").write_text(
        yaml.dump({"columns": ["RU_COL"]}),
        encoding="utf-8",
    )
    (tmp_path / "kanban_schema.en.yaml.example").write_text(
        yaml.dump({"columns": ["EN_COL"]}),
        encoding="utf-8",
    )
    (tmp_path / "kanban_schema.yaml").write_text(
        yaml.dump({"categories": ["work"]}),
        encoding="utf-8",
    )
    merged = load_locale_merged_config(str(tmp_path), "kanban_schema", "en")
    assert merged["columns"] == ["EN_COL"]
    assert merged["categories"] == ["work"]
    clear_runtime_config_cache()
