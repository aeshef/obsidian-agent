#!/usr/bin/env python3
"""Materialize locale YAML from *.example (create or merge missing keys)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from shared.yaml_config import deep_merge, load_yaml
except ImportError:

    def load_yaml(path: Path, default=None):
        if not path.is_file():
            return default if default is not None else {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else (default if default is not None else {})

    def deep_merge(base: dict, override: dict) -> dict:
        out = dict(base)
        for key, val in override.items():
            if key in out and isinstance(out[key], dict) and isinstance(val, dict):
                out[key] = deep_merge(out[key], val)
            else:
                out[key] = val
        return out


def _resolve_locale(locale: str | None) -> str:
    loc = (locale or os.environ.get("AGENT_LOCALE", "en")).strip().lower()
    return "ru" if loc.startswith("ru") else "en"


def _dump_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _example_chain(stem: str, locale: str) -> list[Path]:
    cfg = ROOT / "config"
    loc_path = cfg / f"{stem}.{locale}.yaml.example"
    generic = cfg / f"{stem}.yaml.example"
    # vault_paths: never merge generic EN stub over locale-specific (would create 100_Tasks on RU vaults)
    if stem == "vault_paths":
        if loc_path.is_file():
            return [loc_path]
        return [generic] if generic.is_file() else []
    names = [f"{stem}.{locale}.yaml.example", f"{stem}.yaml.example"]
    return [cfg / n for n in names if (cfg / n).is_file()]


def _merge_examples(paths: list[Path]) -> dict:
    out: dict = {}
    for path in paths:
        data = load_yaml(path, default={})
        if data:
            out = deep_merge(out, data)
    return out


def _materialize_config(stem: str, locale: str, *, refresh_vault_paths: bool = False) -> None:
    examples = _example_chain(stem, locale)
    if not examples:
        return
    ex = _merge_examples(examples)
    if not ex:
        return
    dst = ROOT / "config" / f"{stem}.yaml"
    cur = load_yaml(dst, default={}) if dst.is_file() else {}

    if stem == "vault_paths" and dst.is_file() and cur:
        from shared.capabilities.vault_paths_locale import should_replace_vault_paths_for_locale

        if refresh_vault_paths or should_replace_vault_paths_for_locale(cur, locale):
            _dump_yaml(dst, ex)
            print(f"replaced {dst.relative_to(ROOT)} with {locale} locale example")
            return

    merged = deep_merge(ex, cur) if cur else ex
    if merged == cur and dst.is_file():
        print(f"ok {dst.relative_to(ROOT)}")
        return
    if not dst.is_file():
        _dump_yaml(dst, merged)
        print(f"created {dst.relative_to(ROOT)} from example")
    else:
        _dump_yaml(dst, merged)
        print(f"merged {dst.relative_to(ROOT)} <- example (missing keys only)")


def materialize(locale: str | None = None, *, refresh_vault_paths: bool = False) -> None:
    loc = _resolve_locale(locale)
    for stem in (f"messages.{loc}", f"domain_messages.{loc}", "vault_paths"):
        _materialize_config(
            stem,
            loc,
            refresh_vault_paths=refresh_vault_paths if stem == "vault_paths" else False,
        )

    fin_cfg = ROOT / "finance_bot" / "config"
    for base in ("categories_mvp", "income_categories"):
        ex = fin_cfg / f"{base}.{loc}.yaml.example"
        dst = fin_cfg / f"{base}.yaml"
        if ex.is_file() and not dst.is_file():
            shutil.copy2(ex, dst)
            print(f"created {dst.relative_to(ROOT)} from example")

    _copy_locale_example_if_missing(
        fin_cfg / f"dashboard_templates.{loc}.yaml.example",
        fin_cfg / "dashboard_templates.yaml",
        ROOT,
    )

    plan_cfg = ROOT / "planning_bot" / "config"
    _copy_locale_example_if_missing(
        plan_cfg / f"kanban_schema.{loc}.yaml.example",
        plan_cfg / "kanban_schema.yaml",
        ROOT,
    )
    _copy_locale_example_if_missing(
        plan_cfg / "daily_checkin.yaml.example",
        plan_cfg / "daily_checkin.yaml",
        ROOT,
    )


def _copy_locale_example_if_missing(example: Path, dst: Path, root: Path) -> None:
    if not example.is_file() or dst.is_file():
        return
    shutil.copy2(example, dst)
    print(f"created {dst.relative_to(root)} from {example.name}")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("locale", nargs="?", default=None, help="en or ru")
    ap.add_argument(
        "--refresh-vault-paths",
        action="store_true",
        help="Replace vault_paths.yaml from locale example (onboarding)",
    )
    args = ap.parse_args()
    materialize(args.locale, refresh_vault_paths=args.refresh_vault_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
