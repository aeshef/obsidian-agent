#!/usr/bin/env python3
"""Copy locale *.yaml.example → local *.yaml (first run only)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def materialize(locale: str | None = None) -> None:
    loc = (locale or os.environ.get("AGENT_LOCALE", "en")).strip().lower()
    if loc.startswith("en"):
        loc = "en"
    else:
        loc = "ru"
    pairs = (
        (f"messages.{loc}", f"messages.{loc}"),
        (f"domain_messages.{loc}", f"domain_messages.{loc}"),
        ("vault_paths", f"vault_paths.{loc}"),
    )
    for stem, ex_suffix in pairs:
        ex = ROOT / "config" / f"{ex_suffix}.yaml.example"
        dst = ROOT / "config" / f"{stem}.yaml"
        if ex.is_file() and not dst.is_file():
            shutil.copy2(ex, dst)
            print(f"created {dst.relative_to(ROOT)} from example")

    fin_cfg = ROOT / "finance_bot" / "config"
    for base in ("categories_mvp", "income_categories"):
        ex = fin_cfg / f"{base}.{loc}.yaml.example"
        dst = fin_cfg / f"{base}.yaml"
        if ex.is_file() and not dst.is_file():
            shutil.copy2(ex, dst)
            print(f"created {dst.relative_to(ROOT)} from example")


def main() -> int:
    loc = sys.argv[1] if len(sys.argv) > 1 else None
    materialize(loc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
