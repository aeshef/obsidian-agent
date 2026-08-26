#!/usr/bin/env python3
"""Rebuild config/domain_messages.{en,ru}.yaml.example from per-domain packages."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_ORDER = ("shared", "finance", "planning", "knowledge")


def rebuild(locale: str) -> Path:
    merged: dict = {}
    pkg = _ROOT / "config" / "domain_messages" / locale
    for name in _ORDER:
        path = pkg / f"{name}.yaml.example"
        if not path.is_file():
            raise FileNotFoundError(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must be a mapping")
        merged.update(data)
    out = _ROOT / "config" / f"domain_messages.{locale}.yaml.example"
    header = (
        f"# AUTO-GENERATED from config/domain_messages/{locale}/*.yaml.example — do not edit by hand.\n"
        f"# Edit packages, then: python3 scripts/rebuild_domain_messages.py\n\n"
    )
    body = yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, width=120)
    out.write_text(header + body, encoding="utf-8")
    return out


def main() -> int:
    for loc in ("en", "ru"):
        path = rebuild(loc)
        print(f"wrote {path.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
