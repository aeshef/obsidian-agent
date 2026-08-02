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
_sync_filter_force_push_tasks_safe() {
  local list_file="${1:-}"
  local tasks_root="${2:-}"
  [ -n "$list_file" ] && [ -f "$list_file" ] && [ -n "$tasks_root" ] || return 0
  [ -n "${SERVER:-}" ] && [ -n "${SERVER_VAULT:-}" ] || return 0
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
    if missing_on_local:
        removed += 1
        print(
            f"skip force_push {rel}: would drop {len(missing_on_local)} server task id(s)",
            file=sys.stderr,
        )
        continue
    keep.append(rel)

list_file.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
print(len(keep))
if removed:
    print(f"filtered_force_push removed={removed}", file=sys.stderr)
PY_FILTER_FP
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
