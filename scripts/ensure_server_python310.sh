#!/usr/bin/env bash
# Проверка / установка Python 3.10+ на сервере (Debian/Ubuntu).
#
#   ./scripts/ensure_server_python310.sh          # через SSH на $SERVER
#   INSTALL_REBOOT_LOCAL=1 ./scripts/ensure_server_python310.sh  # локально на VPS
set -euo pipefail

if [ -n "${SERVER_BOTS:-}" ] && [ -f "${SERVER_BOTS}/scripts/lib/common.sh" ]; then
  ROOT="${SERVER_BOTS}"
  # shellcheck source=/dev/null
  source "${SERVER_BOTS}/scripts/lib/common.sh"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  # shellcheck source=scripts/lib/common.sh
  source "$ROOT/scripts/lib/common.sh"
  common_load_env "$ROOT"
fi

_has_py310() {
  local py
  py="$(common_python_for_venv)"
  "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

_install_debian() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  if apt-cache show -t bullseye-backports python3.10 >/dev/null 2>&1; then
    echo "📦 bullseye-backports: python3.10 python3.10-venv"
    apt-get install -y -t bullseye-backports python3.10 python3.10-venv python3.10-dev
    return 0
  fi
  if apt-cache show python3.10 >/dev/null 2>&1 && apt-cache show python3.10 | grep -q '^Package: python3.10$'; then
    echo "📦 apt install python3.10 python3.10-venv"
    apt-get install -y python3.10 python3.10-venv python3.10-dev
    return 0
  fi
  return 1
}

_check_install() {
  if _has_py310; then
    echo "✅ Python OK: $(common_python_for_venv -V 2>&1) ($(common_python_for_venv))"
    return 0
  fi
  echo "⚠️  Python >= 3.10 не найден (сейчас: $(python3 -V 2>&1))" >&2
  if command -v apt-get >/dev/null 2>&1; then
    if _install_debian && command -v python3.10 >/dev/null; then
      echo "✅ installed: $(python3.10 -V)"
      return 0
    fi
  fi
  echo "❌ Установите Python 3.10+ (Debian: bullseye-backports) и пересоздайте venv:" >&2
  echo "   scripts/ensure_bot_venv.sh all --recreate" >&2
  return 1
}

if [ -n "${SERVER:-}" ] && [ "${INSTALL_REBOOT_LOCAL:-0}" != 1 ]; then
  common_require_server
  echo "📡 ensure Python 3.10+ on $SERVER ..."
  ssh "$SERVER" "INSTALL_REBOOT_LOCAL=1 SERVER_BOTS='$(common_server_bots)' bash -s" < "$(dirname "${BASH_SOURCE[0]}")/ensure_server_python310.sh"
else
  _check_install
fi
