#!/usr/bin/env bash
# Синхронизирует directory в hubs_registry.yaml с knowledge_subdir() (идемпотентно).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
REG="$ROOT/knowledge_bot/config/hubs_registry.yaml"
EXAMPLE="$ROOT/knowledge_bot/config/hubs_registry.yaml.example"

if [[ ! -f "$REG" && -f "$EXAMPLE" ]]; then
  cp "$EXAMPLE" "$REG"
  echo "created: $REG from example"
fi

PY=python3
for v in "$ROOT/finance_bot/.venv/bin/python" "$ROOT/knowledge_bot/.venv/bin/python"; do
  [[ -x "$v" ]] && PY="$v" && break
done
"$PY" - "$REG" <<'PY'
import sys
from pathlib import Path
import yaml
from shared.vault_layout import knowledge_subdir

path = Path(sys.argv[1])
if not path.is_file():
    sys.exit(0)
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
hubs = data.get("hubs") or []
kd = knowledge_subdir()
from shared.vault_paths_config import vault_rel_path
hubs_name = vault_rel_path("knowledge_hubs")
target = f"{kd}/{hubs_name}"
changed = 0
for hub in hubs:
    if not isinstance(hub, dict):
        continue
    old = hub.get("directory", "")
    if old != target:
        hub["directory"] = target
        changed += 1
if changed:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"updated {changed} hub director(y/ies) → {target}")
else:
    print(f"hubs_registry OK ({target})")
PY
