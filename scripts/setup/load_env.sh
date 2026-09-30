# load-env
# Source repo .env before onboarding shell steps (idempotent).
# Does NOT override keys already set in the environment (demo / CI overlays win).
# Usage (from repo root):
#   source scripts/setup/load_env.sh
_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "$_ROOT/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    # Preserve pre-set env (e.g. AGENT_LOCALE=en for demo-vault builds)
    if [[ -n "${!key+x}" && -n "${!key}" ]]; then
      continue
    fi
    val="${line#*=}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    if [[ ${#val} -ge 2 ]]; then
      q="${val:0:1}"
      if [[ "$q" == '"' || "$q" == "'" ]] && [[ "${val: -1}" == "$q" ]]; then
        val="${val:1:${#val}-2}"
      fi
    fi
    export "$key=$val"
  done < "$_ROOT/.env"
fi
export AGENT_ROOT="${AGENT_ROOT:-$_ROOT}"
