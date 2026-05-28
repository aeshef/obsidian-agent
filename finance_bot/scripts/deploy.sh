#!/usr/bin/env bash
# Делегирует в единый deploy монорепо.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/scripts/deploy.sh" --component finance_bot "$@"
