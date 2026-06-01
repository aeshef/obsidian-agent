#!/bin/zsh
# Скачивает каноническую finance.db с сервера в vault-реплику на Mac для дашборда.
#
# Канон (запись бота): FINANCE_DB_PATH или {REMOTE_BOT_DIR}/finance.db на сервере.
# Реплика (Obsidian):  $VAULT_PATH/300_Дашборды/Данные/finance.db — только pull, не rsync.
#
# По умолчанию ПЕРЕД scp: mirror canonical→vault на сервере + опционально broker sync.
# FINANCE_REFRESH_BROKER_BEFORE_PULL=0 — без broker (каждый obsidian_sync).
# FINANCE_MIRROR_VAULT_ON_SERVER=0 — не трогать vault-копию на VPS.

set -u

if [[ -z "${VAULT_PATH:-}" ]]; then
  if [[ -d "$HOME/Documents/Obsidian Vault" ]]; then
    VAULT_PATH="$HOME/Documents/Obsidian Vault"
  else
    VAULT_PATH="$HOME/Obsidian Vault"
  fi
fi
DATA_DIR="$VAULT_PATH/300_Дашборды/Данные"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a
SERVER="${SERVER:?Set SERVER in .env}"
REMOTE_BOT_DIR="${REMOTE_BOT_DIR:-${SERVER_BOTS:-/root/bots}/finance_bot}"
REMOTE_DB="${REMOTE_DB:-}"
SERVER_VAULT="${SERVER_VAULT:-${SYNC_SERVER_VAULT_PATH:-/root/obsidian-vault}}"

mkdir -p "$DATA_DIR"
SSH_OPTS=(-o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)

_refresh_broker_on_server() {
  [[ "${FINANCE_REFRESH_BROKER_BEFORE_PULL:-1}" == "0" ]] && return 0
  echo "ℹ️ Брокер на сервере: синх перед скачиванием БД…" >&2
  if ssh "${SSH_OPTS[@]}" "$SERVER" \
    "REMOTE_BOT_DIR='${REMOTE_BOT_DIR}' SERVER_BOTS='${SERVER_BOTS:-/root/bots}'" bash -s <<'REMOTE'
set -euo pipefail
cd "${REMOTE_BOT_DIR:?}"
export PYTHONPATH="${REMOTE_BOT_DIR:?}${PYTHONPATH:+:$PYTHONPATH}"
if [ -d ../shared ]; then
  export PYTHONPATH="$(cd .. && pwd):${PYTHONPATH}"
fi
set -a
[[ -f .env ]] && . ./.env
[[ -f ../.env ]] && . ../.env
set +a
if [[ -x .venv/bin/python ]]; then PY=".venv/bin/python"
elif [[ -x venv/bin/python ]]; then PY="venv/bin/python"
else PY="python3"
fi
exec "$PY" scripts/run_broker_sync_once.py
REMOTE
  then
    echo "✅ Брокер на сервере обновлён" >&2
  else
    echo "⚠️ Не удалось обновить брокер по SSH — качаю finance.db как есть." >&2
  fi
}

_mirror_on_server() {
  [[ "${FINANCE_MIRROR_VAULT_ON_SERVER:-1}" == "0" ]] && return 0
  ssh "${SSH_OPTS[@]}" "$SERVER" \
    "REMOTE_BOT_DIR='${REMOTE_BOT_DIR}' SERVER_VAULT='${SERVER_VAULT}' SERVER_BOTS='${SERVER_BOTS:-/root/bots}'" bash -s <<'REMOTE'
set -euo pipefail
cd "${REMOTE_BOT_DIR:?}"
export PYTHONPATH="${REMOTE_BOT_DIR:?}${PYTHONPATH:+:$PYTHONPATH}"
if [ -d ../shared ]; then
  export PYTHONPATH="$(cd .. && pwd):${PYTHONPATH}"
fi
export VAULT_PATH="${SERVER_VAULT}"
set -a
[[ -f .env ]] && . ./.env
[[ -f ../.env ]] && . ../.env
set +a
if [[ -x .venv/bin/python ]]; then PY=".venv/bin/python"
elif [[ -x venv/bin/python ]]; then PY="venv/bin/python"
else PY="python3"
fi
"$PY" -c "from bot.finance_db_paths import mirror_canonical_to_vault_replica; mirror_canonical_to_vault_replica()"
REMOTE
}

resolve_remote_db() {
  ssh "${SSH_OPTS[@]}" "$SERVER" \
    "REMOTE_DB='${REMOTE_DB}' REMOTE_BOT_DIR='${REMOTE_BOT_DIR}' SERVER_BOTS='${SERVER_BOTS:-/root/bots}'" python3 <<'PY'
import os
from pathlib import Path

remote_db = os.environ.get("REMOTE_DB", "").strip()
bot_dir = Path(os.environ.get("REMOTE_BOT_DIR", os.environ.get("SERVER_BOTS", "/root/bots") + "/finance_bot")).expanduser()

def read_env(path: Path) -> dict:
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

env = {}
for p in (bot_dir / ".env", bot_dir.parent / ".env"):
    env.update(read_env(p))

finance_db_path = (env.get("FINANCE_DB_PATH") or remote_db or "").strip()
if finance_db_path:
    p = Path(finance_db_path).expanduser()
    if not p.is_absolute():
        p = (bot_dir / p).resolve()
    if p.is_file():
        print(p)
        raise SystemExit(0)

url = env.get("DATABASE_URL", "sqlite+aiosqlite:///./finance.db")
for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
    if url.startswith(prefix):
        raw = url[len(prefix):].split("?", 1)[0]
        p = Path(raw)
        if not p.is_absolute():
            p = (bot_dir / p).resolve()
        if p.is_file():
            print(p)
            raise SystemExit(0)
        break

fallback = bot_dir / "finance.db"
if fallback.is_file():
    print(fallback.resolve())
    raise SystemExit(0)
raise SystemExit(1)
PY
}

REMOTE_DB_RESOLVED="$REMOTE_DB"
if [ -z "$REMOTE_DB_RESOLVED" ]; then
  REMOTE_DB_RESOLVED="$(resolve_remote_db)"
fi

if [ -z "$REMOTE_DB_RESOLVED" ]; then
  if [ -f "$DATA_DIR/finance.db" ]; then
    echo "⚠️ Не удалось определить каноническую БД на сервере. Локальная реплика: $DATA_DIR/finance.db" >&2
    exit 0
  fi
  echo "❌ Каноническая БД на сервере не найдена и локальной реплики нет." >&2
  exit 1
fi

_refresh_broker_on_server
_mirror_on_server || echo "⚠️ mirror canonical→vault на сервере не удался (продолжаю scp)" >&2

echo "ℹ️ Серверная каноническая БД: $REMOTE_DB_RESOLVED"
if scp "${SSH_OPTS[@]}" "$SERVER:$REMOTE_DB_RESOLVED" "$DATA_DIR/finance.db"; then
  echo "✅ Реплика обновлена: $DATA_DIR/finance.db"
else
  if [ -f "$DATA_DIR/finance.db" ]; then
    echo "⚠️ scp не удался ($REMOTE_DB_RESOLVED). Локальная реплика без изменений." >&2
    exit 0
  fi
  echo "❌ scp не удался и локальной реплики нет." >&2
  exit 1
fi

if [[ "${FINANCE_BUILD_DASHBOARD_AFTER_PULL:-1}" != "0" ]]; then
  echo "ℹ️ Пересборка дашборда (PNG + 📊 Финансы_Дашборд.md)…" >&2
  export VAULT_PATH
  export FINANCE_DB_PATH="$DATA_DIR/finance.db"
  BOT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  if ( cd "$BOT_ROOT" && chmod +x scripts/run_finance_dashboard.sh 2>/dev/null; true ) && \
     ( cd "$BOT_ROOT" && ./scripts/run_finance_dashboard.sh ); then
    echo "✅ Дашборд обновлён" >&2
  else
    echo "⚠️ Дашборд не собран. Запусти: cd \"$BOT_ROOT\" && ./scripts/run_finance_dashboard.sh" >&2
  fi
fi
