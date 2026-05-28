#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Фаза 0 миграции в монорепо: снапшот data plane (страховочная сетка).
#
# Что делает (только ЧИТАЕТ источники, ничего не меняет):
#   1. Тянет с сервера незаменимые данные: finance.db, личные config/*.txt|yaml,
#      индексы knowledge_bot/data/, три .env (секреты).
#   2. Делает git bundle каждого из трёх репозиториев (полная история кода —
#      восстановимо даже после subtree-мержа и force-push).
#   3. Снимает .sync/ маркеры из вольта (идемпотентность инкрементальных шагов).
#   4. Пишет manifest.txt: git SHA каждого репо, PID ботов, размеры, дата.
#
# Снапшот кладётся ВНЕ вольта (не попадёт в rsync на сервер).
# Запускать на Mac. Идемпотентно — каждый запуск создаёт новый таймстемпнутый каталог.
#
# Usage:
#   ./snapshot_data_plane.sh                # снапшот в ~/obsidian-migration-snapshots/<ts>
#   SNAPSHOT_ROOT=/path ./snapshot_data_plane.sh
#   WITH_VAULT_TAR=1 ./snapshot_data_plane.sh   # + полный tar вольта (~12G, нужно место)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Конфиг (можно переопределить через env) ────────────────────────────────
VAULT_PATH="${VAULT_PATH:-/Users/example/Documents/Obsidian Vault}"
AGENT_DIR="${AGENT_DIR:-$VAULT_PATH/800_Автоматизация/Agent}"
SSH_HOST="${SSH_HOST:-example-server}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_obsidian}"
SSH_RSH="ssh -o UseKeychain=yes -o StrictHostKeyChecking=accept-new -i $SSH_KEY"
REMOTE_BOTS="${REMOTE_BOTS:-/root/bots}"
SNAPSHOT_ROOT="${SNAPSHOT_ROOT:-$HOME/obsidian-migration-snapshots}"
WITH_VAULT_TAR="${WITH_VAULT_TAR:-0}"

TS="$(date +%Y-%m-%d_%H%M%S)"
DEST="$SNAPSHOT_ROOT/$TS"

REPOS=(finance_bot knowledge_bot planning_bot)

log() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn(){ printf '\033[1;33m! %s\033[0m\n' "$*"; }

mkdir -p "$DEST"/{server,bundles,vault}
# macOS rsync (2.6.9) не создаёт промежуточные родительские каталоги назначения —
# предсоздаём их явно, иначе копии молча падают.
for r in "${REPOS[@]}"; do mkdir -p "$DEST/server/$r/config" "$DEST/server/$r/data"; done
log "Снапшот → $DEST"

# ── 1. Незаменимые данные с сервера ─────────────────────────────────────────
log "Тяну data plane с $SSH_HOST:$REMOTE_BOTS"

# finance.db — главная БД
rsync -az -e "$SSH_RSH" \
  "$SSH_HOST:$REMOTE_BOTS/finance_bot/finance.db" \
  "$DEST/server/finance_bot/" 2>/dev/null \
  && ok "finance.db" || warn "finance.db не найдена"

# Личные config/* (txt-промпты + yaml вне git: badge, initial_accounts, и т.п.)
rsync -az -e "$SSH_RSH" \
  --include='*.txt' --include='*.yaml' --include='*.yml' --exclude='*' \
  "$SSH_HOST:$REMOTE_BOTS/finance_bot/config/" \
  "$DEST/server/finance_bot/config/" 2>/dev/null \
  && ok "finance_bot/config (личные prompts+yaml)" || warn "config не скопирован"

# knowledge индексы
rsync -az -e "$SSH_RSH" \
  "$SSH_HOST:$REMOTE_BOTS/knowledge_bot/data/" \
  "$DEST/server/knowledge_bot/data/" 2>/dev/null \
  && ok "knowledge_bot/data (индексы)" || warn "knowledge data не скопирован"

# planning_bot data (если есть)
rsync -az -e "$SSH_RSH" \
  "$SSH_HOST:$REMOTE_BOTS/planning_bot/data/" \
  "$DEST/server/planning_bot/data/" 2>/dev/null \
  && ok "planning_bot/data" || warn "planning_bot/data нет (норм, если не используется)"

# .env секреты всех трёх ботов
for r in "${REPOS[@]}"; do
  rsync -az -e "$SSH_RSH" \
    "$SSH_HOST:$REMOTE_BOTS/$r/.env" \
    "$DEST/server/$r/.env" 2>/dev/null \
    && ok ".env: $r" || warn ".env: $r не найден"
done

# ── 2. git bundle каждого репо (полная история) ─────────────────────────────
log "git bundle (история кода)"
for r in "${REPOS[@]}"; do
  if [ -d "$AGENT_DIR/$r/.git" ]; then
    git -C "$AGENT_DIR/$r" bundle create "$DEST/bundles/$r.bundle" --all >/dev/null 2>&1 \
      && ok "bundle: $r ($(git -C "$AGENT_DIR/$r" rev-parse --short HEAD))" \
      || warn "bundle: $r не создан"
  else
    warn "$r: не git-репозиторий, пропуск bundle"
  fi
done

# ── 3. .sync/ маркеры из вольта ─────────────────────────────────────────────
if [ -d "$VAULT_PATH/.sync" ]; then
  rsync -a "$VAULT_PATH/.sync/" "$DEST/vault/.sync/" 2>/dev/null \
    && ok ".sync/ маркеры" || warn ".sync/ не скопирован"
fi

# ── 4. (опц.) Полный tar вольта ─────────────────────────────────────────────
if [ "$WITH_VAULT_TAR" = "1" ]; then
  log "Полный tar вольта (может занять время и ~12G)"
  tar -czf "$DEST/vault/vault_full.tar.gz" \
    --exclude='.git' --exclude='800_Автоматизация/Agent/*/.venv' \
    -C "$(dirname "$VAULT_PATH")" "$(basename "$VAULT_PATH")" \
    && ok "vault_full.tar.gz" || warn "tar вольта не удался"
fi

# ── 5. Manifest ─────────────────────────────────────────────────────────────
log "Manifest"
{
  echo "# Snapshot manifest — $TS"
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "vault_path: $VAULT_PATH"
  echo "ssh_host: $SSH_HOST"
  echo
  echo "## git HEADs (локальные репо)"
  for r in "${REPOS[@]}"; do
    if [ -d "$AGENT_DIR/$r/.git" ]; then
      printf '  %-15s %s  (%s)\n' "$r" \
        "$(git -C "$AGENT_DIR/$r" rev-parse HEAD)" \
        "$(git -C "$AGENT_DIR/$r" rev-parse --abbrev-ref HEAD)"
    fi
  done
  echo
  echo "## боты на сервере (на момент снапшота)"
  $SSH_RSH "$SSH_HOST" "pgrep -af 'start_bot|planning_bot|bot.main' | grep -v pgrep" 2>/dev/null || echo "  (не удалось получить)"
  echo
  echo "## размеры снапшота"
  du -sh "$DEST"/* 2>/dev/null
  echo
  echo "## RESTORE (если что-то пошло не так)"
  echo "# finance.db:        rsync -az server/finance_bot/finance.db  $SSH_HOST:$REMOTE_BOTS/finance_bot/"
  echo "# config:            rsync -az server/finance_bot/config/     $SSH_HOST:$REMOTE_BOTS/finance_bot/config/"
  echo "# knowledge индексы: rsync -az server/knowledge_bot/data/     $SSH_HOST:$REMOTE_BOTS/knowledge_bot/data/"
  echo "# .env:              rsync -az server/<bot>/.env              $SSH_HOST:$REMOTE_BOTS/<bot>/.env"
  echo "# код из bundle:     git clone bundles/<bot>.bundle restored_<bot>"
} > "$DEST/manifest.txt"

cat "$DEST/manifest.txt"
echo
ok "Снапшот готов: $DEST"
echo "  Размер: $(du -sh "$DEST" | cut -f1)"
