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

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
if [[ -z "${VAULT_PATH:-}" ]]; then
  VAULT_PATH="$(common_resolve_vault "$ROOT" 2>/dev/null || true)"
fi
if [[ -z "${VAULT_PATH:-}" ]]; then
  echo "sync_finance_db: VAULT_PATH is not configured" >&2
  exit 1
fi
# shellcheck source=scripts/lib/vault_paths_defaults.sh
source "$ROOT/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "$ROOT" || true
DATA_DIR="$VAULT_PATH/${VAULT_FOLDER_DASHBOARDS:-300_Dashboards}/${VAULT_DASH_DATA:-Data}"
SERVER="${SERVER:?Set SERVER in .env}"
SERVER_BOTS="${SERVER_BOTS:-$(common_server_bots "$ROOT")}"
SERVER_VAULT="${SERVER_VAULT:-${SYNC_SERVER_VAULT_PATH:-$(common_server_vault "$ROOT")}}"
if [[ -z "${SERVER_BOTS:-}" || -z "${SERVER_VAULT:-}" ]]; then
  echo "sync_finance_db: server paths are not configured" >&2
  exit 1
fi
REMOTE_BOT_DIR="${REMOTE_BOT_DIR:-${SERVER_BOTS}/finance_bot}"
REMOTE_DB="${REMOTE_DB:-}"

mkdir -p "$DATA_DIR"
SSH_OPTS=(-o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)

_refresh_broker_on_server() {
  [[ "${FINANCE_REFRESH_BROKER_BEFORE_PULL:-1}" == "0" ]] && return 0
  echo "Broker sync on server before downloading finance.db..." >&2
  if ssh "${SSH_OPTS[@]}" "$SERVER" \
    "REMOTE_BOT_DIR='${REMOTE_BOT_DIR}' SERVER_BOTS='${SERVER_BOTS}'" bash -s <<'REMOTE'
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
    echo "Server broker data updated." >&2
  else
    echo "WARN: broker sync over SSH failed; downloading current finance.db." >&2
  fi
}

_mirror_on_server() {
  [[ "${FINANCE_MIRROR_VAULT_ON_SERVER:-1}" == "0" ]] && return 0
  ssh "${SSH_OPTS[@]}" "$SERVER" \
    "REMOTE_BOT_DIR='${REMOTE_BOT_DIR}' SERVER_VAULT='${SERVER_VAULT}' SERVER_BOTS='${SERVER_BOTS}'" bash -s <<'REMOTE'
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
    "REMOTE_DB='${REMOTE_DB}' REMOTE_BOT_DIR='${REMOTE_BOT_DIR}' SERVER_BOTS='${SERVER_BOTS}'" python3 <<'PY'
import os
from pathlib import Path

remote_db = os.environ.get("REMOTE_DB", "").strip()
bot_dir = Path(os.environ.get("REMOTE_BOT_DIR") or (os.environ["SERVER_BOTS"] + "/finance_bot")).expanduser()

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
    echo "WARN: canonical server DB was not resolved. Keeping local replica: $DATA_DIR/finance.db" >&2
    exit 0
  fi
  echo "ERROR: canonical server DB was not found and no local replica exists." >&2
  exit 1
fi

_refresh_broker_on_server
_mirror_on_server || echo "WARN: server canonical-to-vault mirror failed; continuing with scp." >&2

if [ -f "$DATA_DIR/finance.db" ]; then
  _bak="$DATA_DIR/finance.db.bak.$(date +%Y%m%d_%H%M%S)"
  cp -f "$DATA_DIR/finance.db" "$_bak"
  echo "Backup: $_bak" >&2
  ls -1t "$DATA_DIR"/finance.db.bak.* 2>/dev/null | tail -n +6 | while IFS= read -r _old; do
    [ -n "$_old" ] && rm -f "$_old"
  done
  unset _bak _old
fi

echo "Server canonical DB: $REMOTE_DB_RESOLVED"
if scp "${SSH_OPTS[@]}" "$SERVER:$REMOTE_DB_RESOLVED" "$DATA_DIR/finance.db"; then
  echo "Replica updated: $DATA_DIR/finance.db"
else
  if [ -f "$DATA_DIR/finance.db" ]; then
    echo "WARN: scp failed ($REMOTE_DB_RESOLVED). Local replica left unchanged." >&2
    exit 0
  fi
  echo "ERROR: scp failed and no local replica exists." >&2
  exit 1
fi

if [[ "${FINANCE_BUILD_DASHBOARD_AFTER_PULL:-1}" != "0" ]]; then
  echo "Rebuilding finance dashboard..." >&2
  export VAULT_PATH
  export FINANCE_DB_PATH="$DATA_DIR/finance.db"
  BOT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  if ( cd "$BOT_ROOT" && chmod +x scripts/run_finance_dashboard.sh 2>/dev/null; true ) && \
     ( cd "$BOT_ROOT" && ./scripts/run_finance_dashboard.sh ); then
    echo "Dashboard updated." >&2
  else
    echo "WARN: dashboard was not built. Run: cd \"$BOT_ROOT\" && ./scripts/run_finance_dashboard.sh" >&2
  fi
fi
