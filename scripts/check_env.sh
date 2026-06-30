#!/usr/bin/env bash
# Проверка обязательных переменных в корневом .env.
# Usage: scripts/check_env.sh [mac-sync|deploy|server|all]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"

MODE="${1:-all}"
MISSING=0
WARN=0

_has() {
  local key="$1"
  eval "local v=\${${key}:-}"
  [ -n "$v" ]
}

_require() {
  local key="$1" ctx="$2"
  if _has "$key"; then
    echo "  ok  $key"
  else
    echo "  MISSING  $key  ($ctx)" >&2
    MISSING=$((MISSING + 1))
  fi
}

_warn_if_empty() {
  local key="$1" ctx="$2"
  if _has "$key"; then
    echo "  ok  $key"
  else
    echo "  warn  $key не задан ($ctx)" >&2
    WARN=$((WARN + 1))
  fi
}

_check_mac_sync() {
  echo "=== mac-sync (obsidian_sync на Mac) ==="
  _require SERVER "SSH host для rsync"
  _require VAULT_PATH "локальный vault"
  _warn_if_empty GMAIL_IMAP_USER "шаг 5b.4 iPhone mail IMAP"
  _warn_if_empty GMAIL_IMAP_APP_PASSWORD "шаг 5b.4 iPhone mail IMAP"
  _warn_if_empty OPENROUTER_API_KEY "knowledge vision (опционально)"
  if _has MOBILE_VAULT; then
    echo "  ok  MOBILE_VAULT"
  elif mobile_path="$(common_platform_value "$ROOT" vault mobile_path "" 2>/dev/null || true)" && [ -n "$mobile_path" ]; then
    echo "  ok  vault.mobile_path (platform.yaml)"
  else
    echo "  warn  MOBILE_VAULT / vault.mobile_path не задан (шаг 5e mobile export)" >&2
    WARN=$((WARN + 1))
  fi
}

_check_deploy() {
  echo "=== deploy ==="
  _require SERVER "scripts/deploy.sh"
  _warn_if_empty SERVER_BOTS "or config/agent/platform.yaml server.bots_root"
  _warn_if_empty SERVER_VAULT "or config/agent/platform.yaml server.vault_path"
}

_check_server() {
  echo "=== server (боты на VPS) ==="
  _warn_if_empty TELEGRAM_PLANNING_BOT_TOKEN "planning_bot"
  _warn_if_empty TELEGRAM_KNOWLEDGE_BOT_TOKEN "knowledge_bot"
  _warn_if_empty TELEGRAM_FINANCE_BOT_TOKEN "finance_bot"
  _require DEEPSEEK_API_KEY "LLM (или DEEPSEEK_API_TOKEN)"
  if ! _has DEEPSEEK_API_KEY; then
    _require DEEPSEEK_API_TOKEN "LLM fallback"
  fi
  _warn_if_empty TELEGRAM_USER_ID "knowledge_bot alerts"
}

case "$MODE" in
  mac-sync) _check_mac_sync ;;
  deploy)   _check_deploy ;;
  server)   _check_server ;;
  all)
    _check_mac_sync
    echo
    _check_deploy
    echo
    _check_server
    ;;
  *)
    echo "Usage: $0 [mac-sync|deploy|server|all]" >&2
    exit 2
    ;;
esac

echo
if [ "$MISSING" -gt 0 ]; then
  echo "FAIL: $MISSING обязательных переменных отсутствует. Заполни $ROOT/.env (шаблон: .env.example)" >&2
  exit 1
fi
if [ "$WARN" -gt 0 ]; then
  echo "OK с предупреждениями: $WARN опциональных переменных не задано."
  exit 0
fi
echo "OK: все проверенные переменные заданы."
