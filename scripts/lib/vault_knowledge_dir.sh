# shellcheck shell=bash
# Knowledge vault subdir: VAULT_REL_KNOWLEDGE → platform.yaml → fallback 700_База_Данных
vault_knowledge_subdir() {
  if [[ -n "${VAULT_REL_KNOWLEDGE:-}" ]]; then
    printf '%s\n' "${VAULT_REL_KNOWLEDGE//\/}"
    return 0
  fi
  if [[ -z "${AGENT_ROOT:-}" || ! -d "${AGENT_ROOT}" ]]; then
    printf '%s\n' "700_База_Данных"
    return 0
  fi
  local out
  out="$(
    AGENT_ROOT="$AGENT_ROOT" PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY' 2>/dev/null
import os, sys
root = os.environ.get("AGENT_ROOT", "")
if root and root not in sys.path:
    sys.path.insert(0, root)
from shared.vault_layout import knowledge_subdir
print(knowledge_subdir())
PY
  )"
  if [[ -n "$out" ]]; then
    printf '%s\n' "$out"
  else
    printf '%s\n' "700_База_Данных"
  fi
}
