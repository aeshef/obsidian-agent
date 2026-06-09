"""Regression: KB save path, LLM enums JSON, maintenance dup metrics, extract imports."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_bot.core.config import templates_path_for_vault
from knowledge_bot.core.settings import EnumsConfig, enums_for_llm_payload
from knowledge_bot.services.extract import VisionRateLimitError
from knowledge_bot.services.maintenance_metrics import extract_step_metrics


def test_enums_for_llm_payload_is_json_serializable():
    cfg = EnumsConfig(
        namespaces_controlled=frozenset({"topic", "status"}),
        common={"status": ["draft", "done"]},
        per_type={"knowledge": {"topic": ["ai"]}},
        synonyms={},
    )
    payload = enums_for_llm_payload(cfg)
    text = json.dumps(payload, ensure_ascii=False)
    parsed = json.loads(text)
    assert parsed["namespaces_controlled"] == ["status", "topic"]


def test_templates_path_for_vault_points_to_clones(monkeypatch, tmp_path: Path):
    from functools import lru_cache

    from shared import vault_paths_config as vpc
    from shared.yaml_config import load_yaml

    vault = tmp_path / "vault"
    vault.mkdir()
    cfg_dir = Path(__file__).resolve().parent.parent / "config"
    doc = load_yaml(cfg_dir / "vault_paths.ru.yaml.example", default={})
    vpc.vault_paths_config.cache_clear()

    @lru_cache(maxsize=1)
    def _cfg() -> dict:
        return doc

    monkeypatch.setattr(vpc, "vault_paths_config", _cfg)

    expected = (
        vault
        / doc["folders"]["automation"]
        / Path(doc["paths"]["templates_clones"])
    )
    assert templates_path_for_vault(vault) == expected
    assert "Clones" in str(expected)


def test_extract_step_metrics_counts_dryrun_dup_lines():
    stdout = "\n".join(
        [
            "  удалить: foo/bar.png",
            "  удалить: baz/qux.png",
            "Файлов: 2, освобождено ~35.1 МБ",
        ]
    )
    metrics = extract_step_metrics("apply_duplicates_dryrun", stdout)
    assert metrics.get("duplicates_deleted_lines") == 2
    assert metrics.get("duplicates_mb_freed") == pytest.approx(35.1)


def test_vision_rate_limit_error_importable_from_extract():
    assert issubclass(VisionRateLimitError, Exception)
