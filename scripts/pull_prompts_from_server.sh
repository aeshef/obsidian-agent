#!/usr/bin/env bash
# Подтянуть prod prompts/*.txt с VPS (не перезаписывает локальные не-stub файлы).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# shellcheck source=scripts/lib/vault_knowledge_dir.sh
source "$ROOT/scripts/lib/vault_knowledge_dir.sh"

common_load_env "$ROOT" 2>/dev/null || true
SERVER="${SERVER:-}"
SERVER_BOTS="${SERVER_BOTS:-/root/bots}"
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    -h|--help)
      echo "Usage: $0 [--dry-run]"
      exit 0
      ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -z "$SERVER" ]]; then
  echo "skip: SERVER not set in .env" >&2
  exit 0
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
is_stub() {
  python3 - "$1" <<'PY'
import sys
from pathlib import Path
from shared.prompts import _is_comment_stub
p = Path(sys.argv[1])
if not p.is_file():
    sys.exit(1)
sys.exit(0 if _is_comment_stub(p.read_text(encoding="utf-8").strip()) else 1)
PY
}

PROMPT_DIRS=(
  "config/agent/prompts"
  "finance_bot/config/prompts"
  "knowledge_bot/config/prompts"
  "planning_bot/config/prompts"
)

n=0
for rel in "${PROMPT_DIRS[@]}"; do
  remote="$SERVER_BOTS/$rel"
  local_dir="$ROOT/$rel"
  mkdir -p "$local_dir"
  while IFS= read -r rf; do
    [[ -n "$rf" ]] || continue
    [[ -n "$rf" ]] || continue
    base="$(basename "$rf")"
    [[ "$base" == *.example.txt ]] && continue
    dst="$local_dir/$base"
    if [[ -f "$dst" ]] && ! is_stub "$dst"; then
      echo "keep local (not stub): $rel/$base"
      continue
    fi
    if [[ "$DRY" = 1 ]]; then
      echo "would pull: $rel/$base"
      n=$((n + 1))
      continue
    fi
    rsync -az "$SERVER:$rf" "$dst"
    echo "pulled: $rel/$base"
    n=$((n + 1))
  done < <(ssh -o ConnectTimeout=10 "$SERVER" "ls -1 '$remote'/*.txt 2>/dev/null" || true)
done

echo "pull_prompts_from_server: $n file(s)"
