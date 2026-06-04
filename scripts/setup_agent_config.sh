#!/usr/bin/env bash
# Создаёт локальные config/agent/* из *.example (идемпотентно).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="$ROOT/config/agent"
mkdir -p "$CFG/prompts"

copy_if_missing() {
  local src="$1" dst="$2"
  if [[ -f "$dst" ]]; then
    return 0
  fi
  if [[ ! -f "$src" ]]; then
    echo "skip (no example): $src" >&2
    return 0
  fi
  cp "$src" "$dst"
  echo "created: $dst"
}

for ex in "$CFG"/*.example.yaml "$CFG"/*.example.yml; do
  [[ -f "$ex" ]] || continue
  # capabilities.yaml is optional — absent file means full product (see docs/CAPABILITIES.md)
  [[ "$(basename "$ex")" == "capabilities.yaml.example" ]] && continue
  base="${ex%.example.yaml}"
  base="${base%.example.yml}"
  copy_if_missing "$ex" "${base}.yaml"
done

bash "$(dirname "$0")/ensure_bot_prompts.sh"

copy_if_missing "$CFG/user_profile.md.example" "$CFG/user_profile.md"

echo "Agent config ready under $CFG"
