#!/bin/zsh
# Скачивает актуальную finance.db с сервера в локаль для дашборда.
# Запускается из finance_bot. VAULT_PATH можно задать снаружи.

set -u

VAULT_PATH="${VAULT_PATH:-/Users/example/Documents/Obsidian Vault}"
DATA_DIR="$VAULT_PATH/300_Дашборды/Данные"
SERVER="${SERVER:-example-server}"
REMOTE_BOT_DIR="${REMOTE_BOT_DIR:-/root/bots/finance_bot}"
REMOTE_DB="${REMOTE_DB:-}"

mkdir -p "$DATA_DIR"
SSH_OPTS=(-o UseKeychain=yes -o AddKeysToAgent=yes -o ConnectTimeout=10)

resolve_remote_db() {
  ssh "${SSH_OPTS[@]}" "$SERVER" "REMOTE_DB='$REMOTE_DB' REMOTE_BOT_DIR='$REMOTE_BOT_DIR' python3 - <<'PY'
import os
from pathlib import Path

remote_db = os.environ.get('REMOTE_DB', '').strip()
bot_dir = Path(os.environ.get('REMOTE_BOT_DIR', '/root/bots/finance_bot')).expanduser()
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

fallbacks = [
    bot_dir / 'finance.db',
    Path('/root/bots/finance_bot/finance.db'),
    Path('/root/finance.db'),
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
