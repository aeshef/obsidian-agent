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
  # capabilities.yaml: OSS starter on first setup; absent + OBSIDIAN_AGENT_FULL_INSTALL=1 = full product
  if [[ "$(basename "$ex")" == "capabilities.yaml.example" ]]; then
    continue
  fi
  if [[ "$(basename "$ex")" == "capabilities.starter.yaml.example" ]]; then
    continue
  fi
  base="${ex%.example.yaml}"
  base="${base%.example.yml}"
  copy_if_missing "$ex" "${base}.yaml"
done

if [[ ! -f "$CFG/capabilities.yaml" && -f "$CFG/capabilities.starter.yaml.example" ]]; then
  cp "$CFG/capabilities.starter.yaml.example" "$CFG/capabilities.yaml"
  echo "created: $CFG/capabilities.yaml (OSS starter profile)"
fi

bash "$(dirname "$0")/ensure_bot_prompts.sh"

copy_if_missing "$CFG/user_profile.md.example" "$CFG/user_profile.md"

echo "Agent config ready under $CFG"
echo "Personalize (gitignored): config/agent/user_profile.md, config/agent/prompts/*.txt — see skill obsidian-agent-onboarding §6"
