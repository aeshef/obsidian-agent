#!/usr/bin/env bash
# Устаревшее имя → deploy.sh --restart-unified
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/deploy.sh" --restart-unified "$@"
