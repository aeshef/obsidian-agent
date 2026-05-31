#!/usr/bin/env bash
# Устаревшее имя → единый deploy.sh --prod
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/deploy.sh" --prod "$@"
