"""Keep the Obsidian UI label catalogs aligned across locales."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml


CONFIG = Path(__file__).resolve().parents[1] / "config"


def _labels(locale: str) -> dict:
    path = CONFIG / f"obsidian_ui.{locale}.yaml.example"
    catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(catalog, dict), f"{path} must contain a mapping"
    labels = catalog.get("labels")
    assert isinstance(labels, dict), f"{path} must contain a labels mapping"
    return labels


def _leaf_values(mapping: dict, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], object]:
    leaves = {}
    for key, value in mapping.items():
        path = prefix + (str(key),)
        if isinstance(value, dict):
            leaves.update(_leaf_values(value, path))
        else:
            leaves[path] = value
    return leaves


def _errors(en: dict, ru: dict) -> list[str]:
    en_values = _leaf_values(en)
    ru_values = _leaf_values(ru)
    errors = []
    for locale, own, other in (("EN", en_values, ru_values), ("RU", ru_values, en_values)):
        errors.extend(f"{locale} missing labels.{'.'.join(path)}" for path in sorted(other.keys() - own.keys()))
        errors.extend(
            f"{locale} blank or non-string labels.{'.'.join(path)}"
            for path, value in sorted(own.items())
            if not isinstance(value, str) or not value.strip()
        )
    return errors


def test_obsidian_ui_labels_en_ru_key_parity() -> None:
    en, ru = _labels("en"), _labels("ru")
    assert not (errors := _errors(en, ru)), "\n".join(errors)


def test_validator_reports_missing_key_without_changing_catalogs() -> None:
    en, ru = _labels("en"), _labels("ru")
    changed = deepcopy(ru)
    changed.pop("brand")
    assert "RU missing labels.brand" in _errors(en, changed)


def test_validator_reports_blank_label_without_changing_catalogs() -> None:
    en, ru = _labels("en"), _labels("ru")
    changed = deepcopy(en)
    changed["brand"] = "  "
    assert "EN blank or non-string labels.brand" in _errors(changed, ru)
