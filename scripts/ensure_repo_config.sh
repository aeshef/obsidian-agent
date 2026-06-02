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

export ROOT CFG
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


stems = ("vault_paths", "domain_messages")
for stem in stems:
    example = CFG / f"{stem}.yaml.example"
    local = CFG / f"{stem}.yaml"
    if not example.is_file():
        print(f"  skip {stem}: no example")
        continue
    ex = load_yaml(example)
    if not ex:
        print(f"  skip {stem}: empty example")
        continue
    cur = load_yaml(local) if local.is_file() else {}
    if cur is None:
        continue
    merged = deep_merge(ex, cur) if cur else ex
    if merged == cur and local.is_file():
        print(f"  ok {stem}.yaml")
        continue
    if not local.is_file():
        dump_yaml(local, merged)
        print(f"  created {stem}.yaml from example")
    else:
        dump_yaml(local, merged)
        print(f"  merged {stem}.yaml ← example (missing keys only)")
PY

echo "✅ repo config ensured under $CFG"
