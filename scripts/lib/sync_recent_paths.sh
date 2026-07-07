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
