# shellcheck shell=bash
# Recent local path helpers for obsidian_sync (mtime-based conflict protection).

_write_recent_local_paths() {
  local root="${1:-}" since_epoch="${2:-0}" out_file="${3:-}"
  [ -n "$root" ] && [ -d "$root" ] && [ -n "$out_file" ] || return 1
  python3 - "$root" "$since_epoch" "$out_file" <<'PY_RECENT_PATHS'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
since_epoch = float(sys.argv[2] or "0")
out_file = Path(sys.argv[3])
lines: list[str] = []

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d != ".rsync-backup"]
    for name in filenames:
        p = Path(dirpath) / name
        try:
            if p.stat().st_mtime > since_epoch:
                lines.append(p.relative_to(root).as_posix())
        except OSError:
            pass

out_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
print(len(lines))
PY_RECENT_PATHS
}

_write_recent_local_task_paths() {
  _write_recent_local_paths "$@"
}

# Epoch for "recent local task edits" force-push.
# Prefer last successful sync (not a fixed 30m window): after a long outage, Mac edits
# (or a board that still has tasks the VPS lost) must still win once — otherwise
# --update loses to a newer server mtime and step-4 --ignore-times pulls the loss back.
_sync_recent_tasks_since_epoch() {
  local now floor last_ok last_epoch cap
  now="$(date +%s)"
  floor=$((now - 1800))
  cap=$((now - 604800)) # 7d max lookback
  last_ok="$(head -1 "${SYNC_DIR:-}/last_sync_ok.txt" 2>/dev/null | tr -d '\r\n' || true)"
  last_epoch=0
  if [[ -n "$last_ok" ]]; then
    last_epoch="$(
      python3 - "$last_ok" <<'PY' 2>/dev/null || echo 0
import sys
from datetime import datetime
raw = (sys.argv[1] or "").strip()
for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
    try:
        print(int(datetime.strptime(raw[:19] if "T" in raw else raw, fmt).timestamp()))
        raise SystemExit
    except ValueError:
        continue
print(0)
PY
    )"
  fi
  case "$last_epoch" in ''|*[!0-9]*) last_epoch=0 ;; esac
  if [[ "$last_epoch" -gt 0 && "$last_epoch" -lt "$floor" ]]; then
    if [[ "$last_epoch" -lt "$cap" ]]; then
      echo "$cap"
    else
      echo "$last_epoch"
    fi
  else
    echo "$floor"
  fi
}

# Drop kanban board/archive from an ignore-times force-push list when the local
# copy is missing task IDs that still exist on the server (stale Mac clobber).
# IDs already in the closed-tasks archive are not "lost" — strip them from the
# board instead of pushing Done back after monthly archive.
_sync_filter_force_push_tasks_safe() {
  local list_file="${1:-}"
  local tasks_root="${2:-}"
  local helper="${AGENT_ROOT:-}/scripts/lib/sync_kanban_protect.py"
  [ -n "$list_file" ] && [ -f "$list_file" ] && [ -n "$tasks_root" ] || return 0
  [ -n "${SERVER:-}" ] && [ -n "${SERVER_VAULT:-}" ] || return 0
  if [[ -f "$helper" ]]; then
    python3 "$helper" filter-force-push \
      --list-file "$list_file" \
      --tasks-root "$tasks_root" \
      --server "$SERVER" \
      --server-tasks "$SERVER_VAULT/${VAULT_FOLDER_TASKS}" \
      || true
    return 0
  fi
  python3 - "$list_file" "$tasks_root" "$SERVER" "$SERVER_VAULT/${VAULT_FOLDER_TASKS}" <<'PY_FILTER_FP' || true
import re
import subprocess
import sys
from pathlib import Path

list_file = Path(sys.argv[1])
tasks_root = Path(sys.argv[2])
server = sys.argv[3]
server_tasks = sys.argv[4].rstrip("/")
id_re = re.compile(r"🆔\s*ID:\s*([0-9a-fA-F-]{6,})", re.I)

def ids_of(text: str) -> set[str]:
    return {m.group(1).lower() for m in id_re.finditer(text or "")}

lines = [ln.strip() for ln in list_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
keep: list[str] = []
removed = 0
for rel in lines:
    local_path = tasks_root / rel
    try:
        local_text = local_path.read_text(encoding="utf-8")
    except OSError:
        keep.append(rel)
        continue
    local_ids = ids_of(local_text)
    # Only board-like markdown with task IDs needs the safety check.
    if not local_ids or not rel.endswith(".md"):
        keep.append(rel)
        continue
    try:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", server,
             f"cat {server_tasks}/{rel}"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        keep.append(rel)
        continue
    if proc.returncode != 0:
        keep.append(rel)
        continue
    server_ids = ids_of(proc.stdout)
    missing_on_local = server_ids - local_ids
    # A few IDs missing locally ≈ intentional Obsidian deletes → allow push.
    # Many missing ≈ stale Mac about to clobber a healthy server → block.
    _intentional_delete_max = 5
    if missing_on_local and len(missing_on_local) > _intentional_delete_max:
        removed += 1
        print(
            f"skip force_push {rel}: would drop {len(missing_on_local)} server task id(s)",
            file=sys.stderr,
        )
        continue
    if missing_on_local:
        print(
            f"allow force_push {rel}: drop {len(missing_on_local)} id(s) as intentional delete(s)",
            file=sys.stderr,
        )
    keep.append(rel)

list_file.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
print(len(keep))
if removed:
    print(f"filtered_force_push removed={removed}", file=sys.stderr)
PY_FILTER_FP
}

# Build rsync --exclude-from entries for task markdown where LOCAL has task IDs
# that the server copy lacks. Prevents step-4 --ignore-times (or a newer server
# mtime) from shrinking the board after a local restore / create.
# Archived IDs (present in the closed-tasks file) do not count as local-only.
_sync_write_pull_protect_excludes() {
  local tasks_root="${1:-}"
  local out_file="${2:-}"
  local helper="${AGENT_ROOT:-}/scripts/lib/sync_kanban_protect.py"
  [ -n "$tasks_root" ] && [ -d "$tasks_root" ] && [ -n "$out_file" ] || return 1
  [ -n "${SERVER:-}" ] && [ -n "${SERVER_VAULT:-}" ] || return 1
  if [[ -f "$helper" ]]; then
    python3 "$helper" pull-protect \
      --tasks-root "$tasks_root" \
      --out-file "$out_file" \
      --server "$SERVER" \
      --server-tasks "$SERVER_VAULT/${VAULT_FOLDER_TASKS}" \
      || true
    return 0
  fi
  python3 - "$tasks_root" "$out_file" "$SERVER" "$SERVER_VAULT/${VAULT_FOLDER_TASKS}" <<'PY_PULL_PROTECT' || true
import re
import subprocess
import sys
from pathlib import Path

tasks_root = Path(sys.argv[1])
out_file = Path(sys.argv[2])
server = sys.argv[3]
server_tasks = sys.argv[4].rstrip("/")
id_re = re.compile(r"🆔\s*ID:\s*([0-9a-fA-F-]{6,})", re.I)

def ids_of(text: str) -> set[str]:
    return {m.group(1).lower() for m in id_re.finditer(text or "")}

excludes: list[str] = []
for path in tasks_root.rglob("*.md"):
    if ".rsync-backup" in path.parts:
        continue
    try:
        local_text = path.read_text(encoding="utf-8")
    except OSError:
        continue
    local_ids = ids_of(local_text)
    if len(local_ids) < 3:
        continue
    rel = path.relative_to(tasks_root).as_posix()
    try:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", server,
             f"cat {server_tasks}/{rel}"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        continue
    if proc.returncode != 0:
        continue
    server_ids = ids_of(proc.stdout)
    only_local = local_ids - server_ids
    if only_local:
        excludes.append(rel)
        print(
            f"protect pull {rel}: keep {len(only_local)} local-only task id(s)",
            file=sys.stderr,
        )

out_file.write_text("\n".join(excludes) + ("\n" if excludes else ""), encoding="utf-8")
print(len(excludes))
PY_PULL_PROTECT
}

_local_file_mtime_gt() {
  local file_path="$1" since_epoch="$2"
  [ -f "$file_path" ] || return 1
  python3 - "$file_path" "$since_epoch" <<'PY_MTIME_GT'
import sys
from pathlib import Path

p = Path(sys.argv[1])
since = float(sys.argv[2] or "0")
try:
    raise SystemExit(0 if p.stat().st_mtime > since else 1)
except OSError:
    raise SystemExit(1)
PY_MTIME_GT
}
