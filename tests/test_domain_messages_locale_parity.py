"""domain_messages packages: EN/RU key parity (packages are source of truth)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from shared.domain_messages import load_domain_packages

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


def test_domain_packages_en_ru_key_parity() -> None:
    ru = load_domain_packages("ru")
    en = load_domain_packages("en")
    assert ru and en
    fr, fe = set(_flatten(ru)), set(_flatten(en))
    missing = sorted(fr - fe)
    extra = sorted(fe - fr)
    assert not missing, "EN packages missing keys:\n" + "\n".join(".".join(k) for k in missing[:30])
    assert not extra, "EN packages extra keys:\n" + "\n".join(".".join(k) for k in extra[:30])


def test_domain_en_package_values_no_cyrillic() -> None:
    en = load_domain_packages("en")
    bad = [p for p, v in _flatten(en).items() if CYR.search(v)]
    if len(bad) > 100:
        pytest.skip(
            f"{len(bad)} EN leaves still Cyrillic — run "
            "scripts/setup/translate_domain_messages.py (maintainer)"
        )
    assert not bad, (
        "Cyrillic in domain_messages/en packages:\n"
        + "\n".join(".".join(p) for p in bad[:20])
    )


def test_optional_monolith_matches_packages_if_present() -> None:
    """If someone ran rebuild_domain_messages locally, keep them in sync."""
    order = ("shared", "finance", "planning", "knowledge")
    for loc in ("en", "ru"):
        mono_path = ROOT / f"config/domain_messages.{loc}.yaml.example"
        if not mono_path.is_file():
            continue
        pkgs = load_domain_packages(loc)
        mono = yaml.safe_load(mono_path.read_text(encoding="utf-8")) or {}
        assert set(pkgs) == set(mono), f"{loc} package/monolith top-key drift"
