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
  base="${ex%.example.yaml}"
  base="${base%.example.yml}"
  copy_if_missing "$ex" "${base}.yaml"
done

for ex in "$CFG/prompts"/*.example.txt; do
  [[ -f "$ex" ]] || continue
  name="$(basename "$ex" .example.txt)"
  copy_if_missing "$ex" "$CFG/prompts/${name}.txt"
done

copy_if_missing "$CFG/user_profile.md.example" "$CFG/user_profile.md"

echo "Agent config ready under $CFG"
