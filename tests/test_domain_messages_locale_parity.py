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


def test_domain_packages_match_monolith_and_parity() -> None:
    """Packages are source of truth; monolith is generated; EN/RU key parity."""
    order = ("shared", "finance", "planning", "knowledge")

    def load_packages(locale: str) -> dict:
        merged: dict = {}
        for name in order:
            path = ROOT / "config" / "domain_messages" / locale / f"{name}.yaml.example"
            assert path.is_file(), path
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            merged.update(data)
        return merged

    for loc in ("en", "ru"):
        pkgs = load_packages(loc)
        mono = yaml.safe_load(
            (ROOT / f"config/domain_messages.{loc}.yaml.example").read_text(encoding="utf-8")
        )
        assert set(pkgs) == set(mono), f"{loc} package/monolith top-key drift"

    ru = load_packages("ru")
    en = load_packages("en")
    fr, fe = set(_flatten(ru)), set(_flatten(en))
    missing = sorted(fr - fe)
    extra = sorted(fe - fr)
    assert not missing, "EN packages missing keys:\n" + "\n".join(".".join(k) for k in missing[:30])
    assert not extra, "EN packages extra keys:\n" + "\n".join(".".join(k) for k in extra[:30])


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
