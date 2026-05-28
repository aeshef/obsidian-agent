# shellcheck shell=bash
# Общие функции для скриптов монорепо (source из bot scripts или scripts/*).

common_monorepo_root() {
    local here="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
    here="$(cd "$(dirname "$here")" && pwd)"
    if [ -f "$here/../../.env.example" ] || [ -d "$here/../../shared" ]; then
        cd "$here/../.." && pwd
        return
    fi
    if [ -f "$here/../.env.example" ] || [ -d "$here/../shared" ]; then
        cd "$here/.." && pwd
        return
    fi
    echo "$here"
}

common_load_env() {
    local root="${1:-$(common_monorepo_root)}"
    if [ -f "$root/.env" ]; then
        set -a
        # shellcheck disable=SC1091
        source "$root/.env"
        set +a
    fi
}

common_require_server() {
    if [ -z "${SERVER:-}" ]; then
        echo "❌ SERVER не задан. Добавьте SERVER=your-ssh-host в .env" >&2
        exit 1
    fi
}

common_resolve_vault() {
    local root="${1:-$(common_monorepo_root)}"
    common_load_env "$root"
    echo "${VAULT_PATH:-${OBSIDIAN_VAULT_PATH:-${LOCAL_VAULT:-$HOME/Documents/Obsidian Vault}}}"
}

common_resolve_python() {
    local bot_root="$1"
    for v in .venv venv; do
        if [ -x "$bot_root/$v/bin/python" ]; then
            echo "$bot_root/$v/bin/python"
            return 0
        fi
    done
    command -v python3
}

common_ssh() {
    common_require_server
    ssh "$SERVER" "$@"
}
