#!/bin/zsh
# Скачивает актуальную finance.db с сервера в локаль для дашборда.
# Запускается из finance_bot. VAULT_PATH можно задать снаружи.
#
# По умолчанию ПЕРЕД scp дергается синк брокера на сервере (тот же код, что cron в 7:00),
# чтобы балансы Т-Инвест и снимки на «сегодня» в БД были свежие. Отключить:
#   FINANCE_REFRESH_BROKER_BEFORE_PULL=0

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
REMOTE_BOT_DIR="${REMOTE_BOT_DIR:-${SERVER_BOTS:-/opt/obsidian-bots}/finance_bot}"
REMOTE_DB="${REMOTE_DB:-}"

mkdir -p "$DATA_DIR"
SSH_OPTS=(-o UseKeychain=yes -o AddKeysToAgent=yes -o ConnectTimeout=10)

# Обновить брокера на сервере, затем уже качать БД (иначе дашборд видит вчерашний снимок до 7:00).
_refresh_broker_on_server() {
  [[ "${FINANCE_REFRESH_BROKER_BEFORE_PULL:-1}" == "0" ]] && return 0
  echo "ℹ️ Брокер на сервере: синх перед скачиванием БД…" >&2
  if ssh "${SSH_OPTS[@]}" "$SERVER" "REMOTE_BOT_DIR='$REMOTE_BOT_DIR'" bash -s <<'REMOTE'
set -euo pipefail
cd "${REMOTE_BOT_DIR:?}"
export PYTHONPATH="${REMOTE_BOT_DIR:?}${PYTHONPATH:+:$PYTHONPATH}"
set -a
[[ -f .env ]] && . ./.env
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
    echo "⚠️ Не удалось обновить брокер по SSH — качаю finance.db как есть (возможны вчерашние снимки)." >&2
  fi
}

resolve_remote_db() {
  ssh "${SSH_OPTS[@]}" "$SERVER" "REMOTE_DB='$REMOTE_DB' REMOTE_BOT_DIR='$REMOTE_BOT_DIR' python3 - <<'PY'
import os
from pathlib import Path

remote_db = os.environ.get('REMOTE_DB', '').strip()
bot_dir = Path(os.environ.get('REMOTE_BOT_DIR', os.environ.get('SERVER_BOTS', '/opt/obsidian-bots') + '/finance_bot')).expanduser()
candidates = []

def add_candidate(path_str: str) -> None:
    if not path_str:
        return
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (bot_dir / p).resolve()
    if p.exists() and p.is_file():
        candidates.append(p)

if remote_db:
    add_candidate(remote_db)

env_path = bot_dir / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if line.startswith('DATABASE_URL='):
            url = line.split('=', 1)[1].strip().strip('\"').strip(\"'\")
            prefix = 'sqlite+aiosqlite:///'
            if url.startswith(prefix):
                add_candidate(url[len(prefix):])
            elif url.startswith('sqlite:///'):
                add_candidate(url[len('sqlite:///'):])
            break

_bots = os.environ.get('SERVER_BOTS', '/opt/obsidian-bots')
_default_bot = Path(os.environ.get('REMOTE_BOT_DIR', f"{_bots}/finance_bot"))
fallbacks = [
    bot_dir / 'finance.db',
    _default_bot / 'finance.db',
    Path(os.environ.get('REMOTE_DB', '/opt/finance.db')),
]
for p in fallbacks:
    add_candidate(str(p))

for root in [bot_dir, bot_dir.parent]:
    if root.exists():
        for p in root.rglob('finance.db'):
            add_candidate(str(p))

unique = []
seen = set()
for p in candidates:
    s = str(p.resolve())
    if s not in seen:
        seen.add(s)
        unique.append(p.resolve())

if not unique:
    raise SystemExit(1)

best = max(unique, key=lambda p: p.stat().st_mtime)
print(best)
PY" 2>/dev/null
}

REMOTE_DB_RESOLVED="$REMOTE_DB"
if [ -z "$REMOTE_DB_RESOLVED" ]; then
  REMOTE_DB_RESOLVED="$(resolve_remote_db)"
fi

if [ -z "$REMOTE_DB_RESOLVED" ]; then
  if [ -f "$DATA_DIR/finance.db" ]; then
    echo "⚠️ Не удалось определить путь к БД на сервере. Использую локальную копию: $DATA_DIR/finance.db" >&2
    exit 0
  fi
  echo "❌ Не удалось определить путь к БД на сервере и локальной копии нет: $DATA_DIR/finance.db" >&2
  exit 1
fi

_refresh_broker_on_server

echo "ℹ️ Серверная БД: $REMOTE_DB_RESOLVED"
if scp "${SSH_OPTS[@]}" "$SERVER:$REMOTE_DB_RESOLVED" "$DATA_DIR/finance.db"; then
  echo "✅ БД синхронизирована: $DATA_DIR/finance.db"
else
  if [ -f "$DATA_DIR/finance.db" ]; then
    echo "⚠️ Не удалось скачать БД с сервера ($REMOTE_DB_RESOLVED). Использую локальную копию: $DATA_DIR/finance.db" >&2
    exit 0
  fi
  echo "❌ Не удалось скачать БД с сервера ($REMOTE_DB_RESOLVED) и локальной копии нет: $DATA_DIR/finance.db" >&2
  exit 1
fi

# Графики и markdown не входят в scp — пересобираем дашборд (отключить: FINANCE_BUILD_DASHBOARD_AFTER_PULL=0)
if [[ "${FINANCE_BUILD_DASHBOARD_AFTER_PULL:-1}" != "0" ]]; then
  echo "ℹ️ Пересборка дашборда (PNG + 📊 Финансы_Дашборд.md)…" >&2
  export VAULT_PATH
  export FINANCE_DB_PATH="$DATA_DIR/finance.db"
  BOT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  if ( cd "$BOT_ROOT" && chmod +x scripts/run_finance_dashboard.sh 2>/dev/null; true ) && \
     ( cd "$BOT_ROOT" && ./scripts/run_finance_dashboard.sh ); then
    echo "✅ Дашборд обновлён" >&2
  else
    echo "⚠️ Дашборд не собран (нужен matplotlib в venv: pip install matplotlib). Запусти вручную: cd \"$BOT_ROOT\" && ./scripts/run_finance_dashboard.sh" >&2
  fi
fi
