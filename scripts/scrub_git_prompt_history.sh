#!/usr/bin/env bash
# Переписать историю git: убрать боевые тексты промптов из всех коммитов.
# Только **/config/prompts/* и config/agent/prompts/*
#
#   ./scripts/scrub_git_prompt_history.sh --yes
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
YES=0
DRY=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --dry-run) DRY=1 ;;
  esac
done

FILTER_REPO="${FILTER_REPO:-$ROOT/scripts/.git-filter-repo}"
if [ ! -x "$FILTER_REPO" ]; then
  echo "Downloading git-filter-repo..."
  curl -fsSL https://raw.githubusercontent.com/newren/git-filter-repo/main/git-filter-repo -o "$FILTER_REPO"
  chmod +x "$FILTER_REPO"
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repo: $ROOT" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "❌ Working tree must be clean." >&2
  git status --short
  exit 1
fi

CALLBACK_BODY="$ROOT/scripts/.scrub_prompts_callback_body.py"
python3 - "$CALLBACK_BODY" "$ROOT" <<'GEN'
import sys
from pathlib import Path

out_path, root_s = Path(sys.argv[1]), Path(sys.argv[2])
stubs: dict[str, str] = {}
for p in root_s.rglob("*.example.txt"):
    if not p.is_file():
        continue
    rel = p.relative_to(root_s).as_posix()
    if "/config/prompts/" in rel or rel.startswith("config/agent/prompts/"):
        stubs[rel] = p.read_text(encoding="utf-8")

lines = ["# git-filter-repo --file-info-callback BODY (not a full def)\n", "STUBS = {\n"]
for rel in sorted(stubs):
    esc = stubs[rel].replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    lines.append(f'    "{rel}": """{esc}""",\n')
lines.append("}\n\n")
lines.append(
    """
try:
    _fn = filename.decode("utf-8")
except Exception:
    _fn = filename.decode("utf-8", "surrogateescape")
_is_prompt = (
    (_fn.endswith(".example.txt") or _fn.endswith(".txt"))
    and ("/config/prompts/" in _fn or _fn.startswith("config/agent/prompts/"))
)
if not _is_prompt:
    return (filename, mode, blob_id)
_text = STUBS.get(_fn) or (
    "# Prompt: "
    + _fn.split("/")[-1].replace(".example.txt", "").replace(".txt", "")
    + "\\n# Redacted from git history.\\n"
)
blob_id = value.insert_file_with_contents(_text.encode("utf-8"))
return (filename, mode, blob_id)
"""
)
out_path.write_text("".join(lines), encoding="utf-8")
print(f"Wrote {out_path} ({len(stubs)} HEAD stubs)")
GEN

echo "Unique prompt paths in history:"
git log --all --name-only --pretty=format: | python3 -c "
import sys
def ok(p):
    p = p.strip()
    return p and ('/config/prompts/' in p or p.startswith('config/agent/prompts/')) and (p.endswith('.txt') or p.endswith('.example.txt'))
print(len({ln for ln in sys.stdin if ok(ln)}), 'paths')
"

[ "$DRY" = 1 ] && exit 0

if [ "$YES" != 1 ]; then
  read -r -p "Rewrite ALL commits and remove origin remote temporarily? [y/N] " ans
  [[ "${ans,,}" == y ]] || exit 0
fi

REMOTE_URL=""
if git remote get-url origin >/dev/null 2>&1; then
  REMOTE_URL="$(git remote get-url origin)"
fi

echo "Running git-filter-repo..."
"$FILTER_REPO" --force --file-info-callback "$CALLBACK_BODY"

if [ -n "$REMOTE_URL" ]; then
  git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
fi

echo "Sample check (commit before stub migration, if exists):"
git show 33963ad^:finance_bot/config/prompts/nlu_prompt.example.txt 2>/dev/null | head -4 || true

echo ""
echo "✅ Done. Push: git push --force-with-lease origin main"
