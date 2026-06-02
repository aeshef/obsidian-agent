#!/usr/bin/env bash
# Одноразово: убрать из истории git полные тексты промптов в *.example.txt
# (если репо публичное и в старых коммитах утекли prod-промпты).
#
# Требует: pip install git-filter-repo
# ВНИМАНИЕ: переписывает историю → force push: git push --force-with-lease origin main
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repo: $ROOT" >&2
  exit 1
fi

echo "Paths to scrub (replace file contents in all commits with current stub versions):"
git ls-files '*/*.example.txt' 'config/agent/prompts/*.example.txt' 2>/dev/null | head -20

read -r -p "Continue with git filter-repo? [y/N] " ans
[[ "${ans,,}" == y ]] || exit 0

git filter-repo --force --paths-glob '**/config/prompts/*.example.txt' --paths-glob 'config/agent/prompts/*.example.txt' \
  --replace-text <(printf '%s\n' 'regex:.*==>CURRENT') 2>/dev/null || {
  echo "Use: git filter-repo --invert-paths ... or BFG; see https://github.com/newren/git-filter-repo" >&2
  echo "Safer: keep current stubs in HEAD; scrub only if secrets were committed." >&2
  exit 1
}

echo "Done. Run: git push --force-with-lease origin main"
