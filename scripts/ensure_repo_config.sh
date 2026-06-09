#!/usr/bin/env bash
# Merge repo-level config/*.yaml.example → *.yaml (fill missing keys; local values win).
# Safe on prod: never deletes keys, only deep-merges example under existing local.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
CFG="$ROOT/config"

if [ ! -d "$CFG" ]; then
  echo "❌ no config dir: $CFG" >&2
  exit 1
fi

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for bot in finance_bot knowledge_bot planning_bot; do
    if [ -x "$ROOT/$bot/.venv/bin/python" ]; then
      PY="$ROOT/$bot/.venv/bin/python"
      break
    fi
  done
fi
PY="${PY:-python3}"

export ROOT CFG PYTHONPATH="$ROOT:$ROOT/finance_bot${PYTHONPATH:+:$PYTHONPATH}"
"$PY" <<'PY'
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(os.environ["ROOT"])
CFG = Path(os.environ["CFG"])

try:
    from shared.yaml_config import deep_merge
except ImportError:
    def deep_merge(base: dict, override: dict) -> dict:
        out = dict(base)
        for key, val in override.items():
            if key in out and isinstance(out[key], dict) and isinstance(val, dict):
                out[key] = deep_merge(out[key], val)
            else:
                out[key] = val
        return out


def load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"  ⚠️  skip {path.name}: invalid YAML ({e})")
        return None
    return data if isinstance(data, dict) else {}


def dump_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def resolve_locale() -> str:
    raw = os.environ.get("AGENT_LOCALE", "en").strip().lower()
    return "ru" if raw.startswith("ru") else "en"


def example_chain(stem: str, locale: str) -> list[Path]:
    loc_path = CFG / f"{stem}.{locale}.yaml.example"
    generic = CFG / f"{stem}.yaml.example"
    if stem == "vault_paths":
        if loc_path.is_file():
            return [loc_path]
        return [generic] if generic.is_file() else []
    names = [f"{stem}.{locale}.yaml.example", f"{stem}.yaml.example"]
    return [CFG / n for n in names if (CFG / n).is_file()]


def merge_examples(paths: list[Path]) -> dict:
    out: dict = {}
    for path in paths:
        data = load_yaml(path)
        if data:
            out = deep_merge(out, data)
    return out


locale = resolve_locale()
targets: list[tuple[str, list[Path]]] = [
    ("vault_paths", example_chain("vault_paths", locale)),
    (f"domain_messages.{locale}", example_chain(f"domain_messages.{locale}", locale)),
    (f"messages.{locale}", example_chain(f"messages.{locale}", locale)),
]
legacy_dm = CFG / "domain_messages.yaml.example"
if legacy_dm.is_file():
    targets.append(("domain_messages", [legacy_dm]))

for local_stem, examples in targets:
    if not examples:
        print(f"  skip {local_stem}: no example")
        continue
    ex = merge_examples(examples)
    if not ex:
        print(f"  skip {local_stem}: empty example")
        continue
    local = CFG / f"{local_stem}.yaml"
    cur = load_yaml(local) if local.is_file() else {}
    if cur is None:
        continue
    if local_stem == "vault_paths" and cur:
        try:
            from shared.capabilities.vault_paths_locale import should_replace_vault_paths_for_locale
        except ImportError:
            def _default_tasks(locale_name: str) -> str:
                for name in (
                    f"vault_paths.{locale_name}.yaml.example",
                    "vault_paths.yaml.example",
                ):
                    p = CFG / name
                    if not p.is_file():
                        continue
                    data = load_yaml(p)
                    if isinstance(data, dict):
                        folders = data.get("folders")
                        if isinstance(folders, dict) and folders.get("tasks"):
                            return str(folders["tasks"])
                return ""

            def should_replace_vault_paths_for_locale(doc: dict, loc: str) -> bool:
                folders = doc.get("folders") if isinstance(doc.get("folders"), dict) else {}
                cur_tasks = str(folders.get("tasks", ""))
                other = "en" if loc.startswith("ru") else "ru"
                return bool(cur_tasks) and cur_tasks == _default_tasks(other)

        if should_replace_vault_paths_for_locale(cur, locale):
            dump_yaml(local, ex)
            print(f"  replaced {local_stem}.yaml (wrong-locale default → {locale})")
            continue
    merged = deep_merge(ex, cur) if cur else ex
    if merged == cur and local.is_file():
        print(f"  ok {local_stem}.yaml")
        continue
    if not local.is_file():
        dump_yaml(local, merged)
        print(f"  created {local_stem}.yaml from example")
    else:
        dump_yaml(local, merged)
        print(f"  merged {local_stem}.yaml <- example (missing keys only)")
PY

echo "✅ repo config ensured under $CFG"
