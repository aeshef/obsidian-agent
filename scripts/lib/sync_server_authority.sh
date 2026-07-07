# shellcheck shell=bash
# Protect server-authoritative dashboard JSON from rsync races (clock skew, during-sync edits).

# Basenames under VAULT_FOLDER_DASHBOARDS — normally VPS-owned; recent local edits are preserved.
SYNC_SERVER_AUTHORITY_JSON=(
  goals_task_mapping.json
  kanban_state.json
  kanban_archive_meta.json
  .kanban_monitor_state.json
)

_sync_collect_recent_authority_json() {
  local since_epoch="$1" out_file="$2"
  local dash_root="${LOCAL_VAULT:?}/${VAULT_FOLDER_DASHBOARDS:?}"
  local name rel target
  [ -n "$out_file" ] || return 1
  : >"$out_file"
  for name in "${SYNC_SERVER_AUTHORITY_JSON[@]}"; do
    target="$dash_root/$name"
    if _local_file_mtime_gt "$target" "$since_epoch"; then
      rel="$name"
      printf '%s\n' "$rel" >>"$out_file"
    fi
  done
  wc -l <"$out_file" 2>/dev/null | tr -d ' '
}

_sync_force_push_recent_authority_json() {
  local since_epoch="$1"
  local dash_local="${LOCAL_VAULT:?}/${VAULT_FOLDER_DASHBOARDS:?}"
  local list_file count name
  list_file="$(mktemp "${TMPDIR:-/tmp}/obsidian_sync_authority_push.XXXXXX")"
  count="$(_sync_collect_recent_authority_json "$since_epoch" "$list_file" 2>/dev/null || echo 0)"
  if [ "${count:-0}" -gt 0 ]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=2 force_push_authority_json count=${count}" >> "$DEBUG_LOG" 2>/dev/null || true
    while IFS= read -r name; do
      [ -n "$name" ] || continue
      [ -f "$dash_local/$name" ] || continue
      "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --ignore-times \
        "$dash_local/$name" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/$name" || SYNC_OK=0
    done <"$list_file"
  fi
  rm -f "$list_file" 2>/dev/null || true
}

_sync_authority_pull_excludes() {
  local since_epoch="$1"
  local -a flags=()
  local dash_root="${LOCAL_VAULT:?}/${VAULT_FOLDER_DASHBOARDS:?}"
  local name target
  for name in "${SYNC_SERVER_AUTHORITY_JSON[@]}"; do
    target="$dash_root/$name"
    if _local_file_mtime_gt "$target" "$since_epoch"; then
      flags+=(--exclude="$name")
    fi
  done
  printf '%s\n' "${flags[@]}"
}
