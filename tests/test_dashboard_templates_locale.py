from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIN_CFG = ROOT / "finance_bot" / "config"


def _load(name: str) -> dict:
    data = yaml.safe_load((FIN_CFG / name).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _keys_tree(obj: object, prefix: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            out.add(path)
            out |= _keys_tree(v, path)
    return out


def test_dashboard_templates_en_has_same_key_tree_as_ru():
    ru = _load("dashboard_templates.ru.yaml.example")
    en = _load("dashboard_templates.en.yaml.example")
    ru_keys = _keys_tree(ru)
    en_keys = _keys_tree(en)
    missing = sorted(ru_keys - en_keys)
    assert not missing, f"EN dashboard_templates missing keys: {missing[:20]}"
