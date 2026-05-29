# shellcheck shell=bash
# Общие функции для скриптов монорепо (source из bot scripts или scripts/*).

# Канонический дефолт SERVER_BOTS (prod: /root/bots; override через .env)
readonly COMMON_SERVER_BOTS_DEFAULT="/root/bots"
readonly COMMON_SERVER_VAULT_DEFAULT="/root/obsidian-vault"

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

common_server_bots() {
    echo "${SERVER_BOTS:-$COMMON_SERVER_BOTS_DEFAULT}"
}

common_server_vault() {
    echo "${SERVER_VAULT:-$COMMON_SERVER_VAULT_DEFAULT}"
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

common_python_for_venv() {
    local py
    for py in python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    echo "python3"
}

common_require_python_min() {
    local py="${1:?python required}"
    local major="${2:?major required}"
    local minor="${3:?minor required}"
    "$py" -c "import sys; sys.exit(0 if sys.version_info >= ($major, $minor) else 1)" 2>/dev/null
}

common_ensure_bot_venv() {
    local bot_root="$1"
    if [ -x "$bot_root/.venv/bin/python" ]; then
        return 0
    fi
    if [ -x "$bot_root/venv/bin/python" ] && [ ! -e "$bot_root/.venv" ]; then
        ln -sfn venv "$bot_root/.venv"
    fi
}

common_ssh() {
    common_require_server
    ssh "$SERVER" "$@"
}

# Паттерны pgrep для post-deploy verify
common_bot_pgrep_pattern() {
    case "$1" in
        finance_bot)   echo 'python.*bot.main|bot.main' ;;
        knowledge_bot) echo 'venv/bin/python start_bot|start_bot.py' ;;
        planning_bot)  echo 'planning_bot.app.bot' ;;
        *) echo '' ;;
    esac
}
