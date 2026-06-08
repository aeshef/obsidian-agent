# shellcheck shell=bash
# Bootstrap PYTHONPATH, .env and PYTHON_CMD for monorepo bots.
# Usage (source from run.sh):
#   source "$MONOREPO/scripts/lib/bootstrap_python.sh"
#   bootstrap_python finance_bot

# shellcheck source=scripts/lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
# shellcheck source=scripts/lib/sh_msg.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sh_msg.sh"

bootstrap_python() {
    local component="${1:?component required: finance_bot|knowledge_bot|planning_bot}"
    local monorepo bot_root
    monorepo="$(common_monorepo_root)"
    bot_root="$monorepo/$component"

    if [ ! -d "$bot_root" ]; then
        echo "$(sh_msgf scripts.bootstrap.bot_root_missing "{\"bot_root\":\"$bot_root\"}")" >&2
        return 1
    fi

    common_load_env "$monorepo"
    if [ -f "$bot_root/.env" ]; then
        set -a
        # shellcheck disable=SC1091
        source "$bot_root/.env"
        set +a
    fi

    common_ensure_bot_venv "$bot_root"

    export ROOT="$bot_root"
    export MONOREPO="$monorepo"
    export BOT_COMPONENT="$component"
    export PYTHON_CMD
    PYTHON_CMD="$(common_resolve_python "$bot_root")"
    export PYTHONPATH="$bot_root:$monorepo${PYTHONPATH:+:$PYTHONPATH}"

    if ! common_require_python_min "$PYTHON_CMD" 3 9; then
        echo "$(sh_msgf scripts.bootstrap.python_version "{\"version\":\"$("$PYTHON_CMD" -V 2>&1)\"}")" >&2
        return 1
    fi

    cd "$bot_root"
}
