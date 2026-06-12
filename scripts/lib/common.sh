# shellcheck shell=bash
# Общие функции для скриптов монорепо (source из bot scripts или scripts/*).

if [ -z "${_COMMON_SH_LOADED:-}" ]; then
  readonly COMMON_SERVER_BOTS_DEFAULT="/root/bots"
  readonly COMMON_SERVER_VAULT_DEFAULT="/root/obsidian-vault"
  _COMMON_SH_LOADED=1
fi

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
        # shellcheck source=scripts/lib/sh_msg.sh
        source "$(dirname "${BASH_SOURCE[0]}")/sh_msg.sh"
        echo "$(sh_msg scripts.common.server_not_set)" >&2
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

# site-packages venv (matplotlib/sqlalchemy и т.д.) без активации venv
common_bot_site_packages() {
    local bot_root="$1" v sp
    for v in .venv venv; do
        sp="$(ls -d "$bot_root/$v/lib/python"*/site-packages 2>/dev/null | head -1)"
        if [ -n "$sp" ] && [ -d "$sp" ]; then
            echo "$sp"
            return 0
        fi
    done
    return 1
}

# Версия Python из venv (3.12) — для подбора системного интерпретатора той же minor
common_venv_python_tag() {
    local bot_root="$1" py
    for py in "$bot_root/.venv/bin/python" "$bot_root/venv/bin/python"; do
        if [ -x "$py" ]; then
            "$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null && return 0
        fi
    done
    echo "3.12"
}

# LaunchAgent без FDA не читает Documents/.../.venv/pyvenv.cfg — venv падает на import site.
# Fallback: Homebrew python той же minor + site-packages venv на PYTHONPATH.
common_resolve_python_usable() {
    local bot_root="$1" py ver candidate
    for py in "$bot_root/.venv/bin/python" "$bot_root/venv/bin/python"; do
        if [ -x "$py" ] && "$py" -c "import site" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    ver="$(common_venv_python_tag "$bot_root")"
    for candidate in \
        "/opt/homebrew/bin/python${ver}" \
        "/usr/local/bin/python${ver}" \
        "python${ver}"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            py="$(command -v "$candidate")"
            if "$py" -c "import site" 2>/dev/null; then
                echo "$py"
                return 0
            fi
        fi
    done
    if [ -x "/opt/homebrew/bin/python3" ] && /opt/homebrew/bin/python3 -c "import site" 2>/dev/null; then
        echo "/opt/homebrew/bin/python3"
        return 0
    fi
    command -v python3
}

# Homebrew python той же minor, что venv (не python3 → 3.14 после brew upgrade на Tahoe).
common_launchagent_python() {
    local bot_root="${1:-}" ver py candidate
    if [ -n "$bot_root" ]; then
        ver="$(common_venv_python_tag "$bot_root")"
    else
        ver="3.12"
    fi
    for candidate in \
        "/opt/homebrew/bin/python${ver}" \
        "/usr/local/bin/python${ver}" \
        "python${ver}"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            py="$(command -v "$candidate")"
            if "$py" -c "import site" 2>/dev/null; then
                echo "$py"
                return 0
            fi
        fi
    done
    common_resolve_python_usable "${bot_root:-/nonexistent}"
}

# LaunchAgent без FDA: python не может open() .py в ~/Documents; zsh с FDA читает и шлёт в stdin.
common_run_python_script() {
    local py="$1" script="$2"
    shift 2
    if [ -t 0 ]; then
        "$py" "$script" "$@"
        return $?
    fi
    if [ ! -f "$script" ]; then
        echo "common_run_python_script: missing $script" >&2
        return 1
    fi
    cat "$script" | "$py" -u - "$@"
}

common_export_bot_pythonpath() {
    local bot_root="$1"
    local monorepo="${2:-$(dirname "$bot_root")}"
    local sp extra=""
    if [ -n "${OBSIDIAN_AGENT_PYDEPS_FINANCE:-}" ] && [[ "$bot_root" == *finance_bot* ]]; then
        sp="${OBSIDIAN_AGENT_PYDEPS_FINANCE}"
    elif [ -n "${OBSIDIAN_AGENT_PYDEPS_PLANNING:-}" ] && [[ "$bot_root" == *planning_bot* ]]; then
        sp="${OBSIDIAN_AGENT_PYDEPS_PLANNING}"
    else
        sp="$(common_bot_site_packages "$bot_root" 2>/dev/null || true)"
    fi
    if [ -n "${OBSIDIAN_AGENT_PYDEPS_FINANCE:-}" ] && [[ "$bot_root" == *finance_bot* ]]; then
        extra="${OBSIDIAN_AGENT_PYDEPS_PLANNING:+:$OBSIDIAN_AGENT_PYDEPS_PLANNING}"
    fi
    export PYTHONPATH="$bot_root:$monorepo${sp:+:$sp}${extra}${PYTHONPATH:+:$PYTHONPATH}"
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
        planning_bot)  echo 'planning_bot.app.main' ;;
        *) echo '' ;;
    esac
}
