#!/usr/bin/env python3
"""Merge messages.ru.yaml.example → messages.en.yaml.example (full key parity)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
RU = ROOT / "config" / "messages.ru.yaml.example"
EN = ROOT / "config" / "messages.en.yaml.example"
OVERRIDES = ROOT / "config" / "locale" / "en_by_path.json"
CYR = re.compile(r"[а-яА-ЯёЁ]")


def _set_path(tree: dict, keys: tuple[str, ...], value: str) -> None:
    node = tree
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def _flatten(d: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    out: dict[tuple[str, ...], str] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, prefix + (str(k),)))
    else:
        out[prefix] = str(d)
    return out


def main() -> int:
    ru = yaml.safe_load(RU.read_text(encoding="utf-8")) or {}
    en_existing = yaml.safe_load(EN.read_text(encoding="utf-8")) if EN.is_file() else {}
    if not isinstance(en_existing, dict):
        en_existing = {}

    overrides: dict[str, str] = {}
    if OVERRIDES.is_file():
        overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))

    en_tree: dict = {}
    missing_ov: list[str] = []
    cyr_left: list[str] = []

    flat_en = _flatten(en_existing)
    for path, ru_val in sorted(_flatten(ru).items()):
        dotted = ".".join(path)
        if dotted in overrides:
            val = overrides[dotted]
        elif path in flat_en and flat_en[path] and not CYR.search(flat_en[path]):
            val = flat_en[path]
        else:
            val = None
        if val is None:
            missing_ov.append(dotted)
            val = ru_val
        if CYR.search(val):
            cyr_left.append(dotted)
        _set_path(en_tree, path, val)

    header = (
        "# cp config/messages.en.yaml.example config/messages.en.yaml\n"
        "# Set AGENT_LOCALE=en in .env. Keys must match messages.ru.yaml.example.\n"
        "# Regenerate: python3 scripts/build_messages_en_from_ru.py\n\n"
    )
    EN.write_text(
        header + yaml.dump(en_tree, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )

    print(f"wrote {EN} ({len(_flatten(en_tree))} keys)")
    if missing_ov:
        print(f"WARN: {len(missing_ov)} keys without en_by_path.json override", file=sys.stderr)
    if cyr_left:
        print(f"ERROR: {len(cyr_left)} EN values still contain Cyrillic", file=sys.stderr)
        for p in cyr_left[:20]:
            print(f"  {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
