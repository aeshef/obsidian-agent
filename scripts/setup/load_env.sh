#!/usr/bin/env bash
# Source repo .env before onboarding shell steps (idempotent).
# Usage (from repo root):
#   # load-env
#   source scripts/setup/load_env.sh
set -a
_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "$_ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  source "$_ROOT/.env"
fi
set +a
export AGENT_ROOT="${AGENT_ROOT:-$_ROOT}"
