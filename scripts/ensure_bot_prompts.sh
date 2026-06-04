#!/usr/bin/env bash
# Создаёт локальные config/**/prompts/*.txt из *.example.txt (идемпотентно, не перезаписывает prod).
# В git только *.example.txt (comment-stubs); боевые *.txt — gitignore, обязательны локально и на VPS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh" 2>/dev/null || true

WARN_STUBS=0
CHECK_GIT=0

usage() {
  cat <<'EOF'
Usage: ./scripts/ensure_bot_prompts.sh [options]

  (no options)     copy *.example.txt → *.txt where .txt is missing
  --warn-stubs   warn on stderr for each prod .txt that is still a comment-only stub
  --check-git    exit 1 if git index tracks any prod prompts/*.txt (not *.example.txt)

Prod *.txt are never overwritten. Fill them after first copy from example.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --warn-stubs) WARN_STUBS=1 ;;
    --check-git) CHECK_GIT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

PROMPT_DIRS=(
  "config/agent/prompts"
  "finance_bot/config/prompts"
  "knowledge_bot/config/prompts"
  "planning_bot/config/prompts"
)

copy_if_missing() {
  local src="$1" dst="$2"
  if [[ -f "$dst" ]]; then
    return 0
  fi
  if [[ ! -f "$src" ]]; then
    echo "skip (no example): $src" >&2
    return 0
  fi
  cp "$src" "$dst"
  echo "created: $dst (from example — заполните prod-текст, не коммитьте)"
}

is_comment_stub() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  python3 - "$f" <<'PY'
import sys
from pathlib import Path
from shared.prompts import _is_comment_stub
p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8").strip()
sys.exit(0 if _is_comment_stub(text) else 1)
PY
}

if [[ "$CHECK_GIT" = 1 ]]; then
  cd "$ROOT"
  bad=()
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    case "$p" in
      */prompts/*.txt)
        case "$p" in *.example.txt) continue ;; esac
        bad+=("$p")
        ;;
    esac
  done < <(git ls-files '**/prompts/*.txt' 'config/agent/prompts/*.txt' 2>/dev/null || true)
  if [[ ${#bad[@]} -gt 0 ]]; then
    echo "❌ prod prompt .txt must not be in git:" >&2
    printf '  %s\n' "${bad[@]}" >&2
    exit 1
  fi
  echo "✓ git: no tracked prod prompts/*.txt"
  exit 0
fi

export PYTHONPATH="${PYTHONPATH:-}:$ROOT"

created=0
for rel in "${PROMPT_DIRS[@]}"; do
  dir="$ROOT/$rel"
  [[ -d "$dir" ]] || continue
  for ex in "$dir"/*.example.txt; do
    [[ -f "$ex" ]] || continue
    name="$(basename "$ex" .example.txt)"
    dst="$dir/${name}.txt"
    if [[ ! -f "$dst" ]]; then
      copy_if_missing "$ex" "$dst"
      created=$((created + 1))
    fi
  done
done

# English scaffolds for personalized prompts (prod still stub after example copy)
if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT/scripts/scaffold_personalized_prompts.py" 2>/dev/null || true
fi

if [[ "$WARN_STUBS" = 1 ]]; then
  stubs=()
  for rel in "${PROMPT_DIRS[@]}"; do
    dir="$ROOT/$rel"
    [[ -d "$dir" ]] || continue
    for txt in "$dir"/*.txt; do
      [[ -f "$txt" ]] || continue
      case "$txt" in *.example.txt) continue ;; esac
      if is_comment_stub "$txt"; then
        stubs+=("${txt#$ROOT/}")
      fi
    done
  done
  if [[ ${#stubs[@]} -gt 0 ]]; then
    echo "⚠️  prod prompts still comment-stubs (заполните .txt):" >&2
    printf '  %s\n' "${stubs[@]}" >&2
  fi
fi

echo "Bot prompts ready (created $created from examples)"
