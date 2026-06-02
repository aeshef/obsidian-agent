#!/usr/bin/env bash
# Восстановить боевые prompts/*.txt из старых *.example.txt в git (до comment-stubs).
#
#   ./scripts/recover_prod_prompts_from_git.sh [git-rev] --local
#   ./scripts/recover_prod_prompts_from_git.sh [git-rev] --server
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REV="${1:-4866711}"
TARGET="${2:---local}"

if [[ "$TARGET" != "--local" && "$TARGET" != "--server" ]]; then
  echo "Usage: $0 [git-rev] --local|--server" >&2
  exit 2
fi

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT" 2>/dev/null || true

extract_body() {
  local rel="$1"
  python3 - "$REV" "$rel" "$ROOT" <<'PY'
import subprocess, sys
rev, rel, root = sys.argv[1], sys.argv[2], sys.argv[3]
text = subprocess.check_output(["git", "-C", root, "show", f"{rev}:{rel}"], text=True)
body: list[str] = []
started = False
for ln in text.splitlines():
    s = ln.strip()
    if not started:
        if s and not s.startswith("#"):
            started = True
        continue
    body.append(ln)
out = "\n".join(body).strip()
if not out:
    sys.exit(1)
print(out + "\n")
PY
}

n=0
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  body="$(extract_body "$rel")" || continue
  stem="$(basename "$rel" .example.txt)"
  bot_dir="${rel%%/config/*}"

  if [[ "$TARGET" == "--local" ]]; then
    out="$ROOT/${bot_dir}/config/prompts/${stem}.txt"
    mkdir -p "$(dirname "$out")"
    if [[ -f "$out" ]]; then
      echo "skip (exists): $out"
      continue
    fi
    printf '%s' "$body" >"$out"
    echo "created: $out"
    n=$((n + 1))
    continue
  fi

  common_require_server
  SERVER_BOTS="$(common_server_bots)"
  remote="$SERVER_BOTS/${bot_dir}/config/prompts/${stem}.txt"
  if ssh "$SERVER" "[ -f '$remote' ]"; then
    echo "skip (exists): $remote"
    continue
  fi
  tmp="$(mktemp)"
  printf '%s' "$body" >"$tmp"
  rsync -az "$tmp" "$SERVER:$remote"
  rm -f "$tmp"
  echo "created: $remote"
  n=$((n + 1))
done < <(git -C "$ROOT" ls-tree -r --name-only "$REV" | grep '/config/prompts/.*\.example\.txt$' || true)

echo "✅ recovered $n prompt(s) from $REV ($TARGET)"
