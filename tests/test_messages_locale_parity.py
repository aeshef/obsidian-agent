"""messages.en.yaml.example is the canonical Telegram UI catalog (English-first OSS).

When adding keys, edit messages.en.yaml.example first, then mirror Russian in the same PR.
"""
from __future__ import annotations

import re
from pathlib import Path

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


def test_en_and_ru_same_keys() -> None:
    ru = yaml.safe_load((ROOT / "config/messages.ru.yaml.example").read_text(encoding="utf-8"))
    en = yaml.safe_load((ROOT / "config/messages.en.yaml.example").read_text(encoding="utf-8"))
    fr, fe = set(_flatten(ru)), set(_flatten(en))
    missing_in_en = sorted(fr - fe)
    missing_in_ru = sorted(fe - fr)
    assert not missing_in_en, "EN missing keys:\n" + "\n".join(".".join(k) for k in missing_in_en[:40])
    assert not missing_in_ru, "RU missing keys:\n" + "\n".join(".".join(k) for k in missing_in_ru[:40])


def test_en_values_no_cyrillic() -> None:
    en = yaml.safe_load((ROOT / "config/messages.en.yaml.example").read_text(encoding="utf-8"))
    bad = [p for p, v in _flatten(en).items() if CYR.search(v)]
    assert not bad, "Cyrillic in EN values:\n" + "\n".join(".".join(p) for p in bad[:30])
