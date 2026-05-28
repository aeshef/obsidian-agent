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
  # bullseye-backports убран с deb.debian.org (EOL) → archive.debian.org
  local backports_file="/etc/apt/sources.list.d/bullseye-backports.list"
  if [ -f /etc/apt/sources.list.d/backports.list ]; then
    rm -f /etc/apt/sources.list.d/backports.list
  fi
  if ! grep -q 'archive.debian.org.*bullseye-backports' "$backports_file" 2>/dev/null; then
    echo "📦 enable archive.debian.org bullseye-backports"
    cat > "$backports_file" <<'EOF'
deb [check-valid-until=no] http://archive.debian.org/debian bullseye-backports main
EOF
  fi
  apt-get update -qq
  if apt-cache show -t bullseye-backports python3.10 >/dev/null 2>&1; then
    echo "📦 bullseye-backports: python3.10 python3.10-venv"
    apt-get install -y -t bullseye-backports python3.10 python3.10-venv python3.10-dev
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
  echo "❌ Python 3.10+ недоступен через apt на Debian Bullseye." >&2
  echo "   Варианты: (1) оставить 3.9 — боты работают; (2) pyenv/uv: uv python install 3.11" >&2
  echo "   Затем: scripts/ensure_bot_venv.sh all --recreate" >&2
  return 1
}

if [ -n "${SERVER:-}" ] && [ "${INSTALL_REBOOT_LOCAL:-0}" != 1 ]; then
  common_require_server
  echo "📡 ensure Python 3.10+ on $SERVER ..."
  ssh "$SERVER" "INSTALL_REBOOT_LOCAL=1 SERVER_BOTS='$(common_server_bots)' bash -s" < "$(dirname "${BASH_SOURCE[0]}")/ensure_server_python310.sh"
else
  _check_install
fi
