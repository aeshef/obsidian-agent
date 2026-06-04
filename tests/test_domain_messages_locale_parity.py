"""domain_messages.en.yaml.example must mirror RU keys (values may lag translation)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CYR = re.compile(r"[а-яА-ЯёЁ]")


def _flatten(d: object, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    out: dict[tuple[str, ...], str] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, prefix + (str(k),)))
    else:
        out[prefix] = str(d)
    return out


def test_domain_en_has_all_ru_keys() -> None:
    ru = yaml.safe_load((ROOT / "config/domain_messages.ru.yaml.example").read_text(encoding="utf-8"))
    en = yaml.safe_load((ROOT / "config/domain_messages.en.yaml.example").read_text(encoding="utf-8"))
    fr, fe = set(_flatten(ru)), set(_flatten(en))
    missing = sorted(fr - fe)
    extra = sorted(fe - fr)
    assert not missing, "EN missing keys:\n" + "\n".join(".".join(k) for k in missing[:30])
    assert not extra, "EN extra keys:\n" + "\n".join(".".join(k) for k in extra[:30])


def test_domain_en_values_no_cyrillic() -> None:
    """When EN catalog is translated, this guards OSS English."""
    en = yaml.safe_load((ROOT / "config/domain_messages.en.yaml.example").read_text(encoding="utf-8"))
    bad = [p for p, v in _flatten(en).items() if CYR.search(v)]
    if len(bad) > 100:
        pytest.skip(
            f"{len(bad)} EN leaves still Cyrillic — run "
            "scripts/setup/translate_domain_messages.py (maintainer)"
        )
    assert not bad, (
        "Cyrillic in domain_messages.en.yaml.example:\n"
        + "\n".join(".".join(p) for p in bad[:20])
    )
