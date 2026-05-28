#!/usr/bin/env bash
# Дополняет локальный .env ключами с prod-сервера (не перезаписывает уже заданные локально).
# Usage: scripts/merge_env_from_server.sh [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
common_require_server

LOCAL_ENV="$ROOT/.env"
REMOTE_ENV="${SERVER_BOTS:-/root/bots}/.env"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

if [ ! -f "$LOCAL_ENV" ]; then
  cp "$ROOT/.env.example" "$LOCAL_ENV"
  echo "Создан $LOCAL_ENV из .env.example"
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if ! common_ssh "test -f '$REMOTE_ENV' && cat '$REMOTE_ENV'" > "$TMP"; then
  echo "❌ Не удалось прочитать $REMOTE_ENV на $SERVER" >&2
  exit 1
fi

added=0
skipped=0

while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%$'\r'}"
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" != *=* ]] && continue
  key="${line%%=*}"
  key="${key// /}"
  [[ -z "$key" ]] && continue

  # Уже есть непустое значение локально?
  if grep -qE "^${key}=" "$LOCAL_ENV" 2>/dev/null; then
    local_val="$(grep -E "^${key}=" "$LOCAL_ENV" | tail -1 | cut -d= -f2- | sed 's/^["'\'' ]//;s/["'\'' ]$//')"
    if [ -n "$local_val" ]; then
      skipped=$((skipped + 1))
      continue
    fi
  fi

  remote_val="${line#*=}"
  remote_val="${remote_val#\"}"; remote_val="${remote_val%\"}"
  remote_val="${remote_val#\'}"; remote_val="${remote_val%\'}"
  [ -z "$remote_val" ] && continue

  if [ "$DRY" = 1 ]; then
    echo "would add: $key=***"
  else
    if grep -qE "^${key}=" "$LOCAL_ENV" 2>/dev/null; then
      # заменить пустую строку
      if [[ "$(uname)" == Darwin ]]; then
        sed -i '' "s|^${key}=.*|${key}=${remote_val}|" "$LOCAL_ENV"
      else
        sed -i "s|^${key}=.*|${key}=${remote_val}|" "$LOCAL_ENV"
      fi
    else
      echo "${key}=${remote_val}" >> "$LOCAL_ENV"
    fi
    echo "added: $key"
  fi
  added=$((added + 1))
done < "$TMP"

echo "merge_env_from_server: added=$added skipped_nonempty=$skipped dry_run=$DRY"
