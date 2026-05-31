#!/usr/bin/env bash
# Устаревшее имя → deploy.sh --patch-agent-env
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/deploy.sh" --patch-agent-env "$@"
