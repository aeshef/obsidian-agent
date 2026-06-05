#!/usr/bin/env bash
# One-shot onboarding wizard over obsidian-agent-onboarding skill phases.
# Non-interactive setup steps; secrets still require: python3 scripts/setup/env_tools.py set KEY 'value'
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONIOENCODING=utf-8
AGENT_LOCALE="${AGENT_LOCALE:-en}"

PLAYBOOK=""
MODULES=""
CONNECTOR_FLAGS=()
DRY_RUN=0
SKIP_PROMPTS=0
SKIP_SMOKE=0
WRITE_CAP=1

usage() {
  cat <<'EOF'
Usage: scripts/onboarding_wizard.sh [options]

Guided OSS setup (skill: .cursor/skills/obsidian-agent-onboarding/SKILL.md).

Options:
  --playbook planning|finance|full   Golden path (default: prompt if TTY)
  --modules "planning finance"         Space-separated modules (overrides playbook modules)
  --connectors FLAGS                 Extra apply_capabilities_profile flags (repeatable)
  --locale en|ru                     Default: en
  --dry-run                          apply_capabilities_profile --dry-run only
  --skip-prompts                     Skip ensure_bot_prompts / scaffold
  --skip-smoke                       Skip onboarding_smoke.py
  --no-write-cap                     Do not write capabilities.yaml (author full install)
  -h, --help                         This help

Examples:
  ./scripts/onboarding_wizard.sh --playbook planning
  ./scripts/onboarding_wizard.sh --playbook finance --connectors --broker-sync
  ./scripts/onboarding_wizard.sh --modules knowledge --connectors --knowledge-serendipity

After the wizard: set secrets with scripts/setup/env_tools.py set, then re-run smoke with --require-env.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --playbook) PLAYBOOK="${2:-}"; shift 2 ;;
    --modules) MODULES="${2:-}"; shift 2 ;;
    --connectors) CONNECTOR_FLAGS+=("${2:-}"); shift 2 ;;
    --locale) AGENT_LOCALE="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-prompts) SKIP_PROMPTS=1; shift ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    --no-write-cap) WRITE_CAP=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

PY="${PYTHON:-}"
for bot in finance_bot knowledge_bot planning_bot; do
  if [[ -x "$ROOT/$bot/.venv/bin/python" ]]; then
    PY="$ROOT/$bot/.venv/bin/python"
    break
  fi
done
PY="${PY:-python3}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Phase 0 — detect
log "Phase 0: detect context"
if [[ -f config/agent/capabilities.yaml ]]; then
  echo "capabilities.yaml: present"
else
  echo "capabilities.yaml: absent (full install default on author machine)"
fi
if [[ -f .env ]]; then
  grep -E '^VAULT_PATH=' .env || echo "NEED_ENV: VAULT_PATH"
else
  echo "NEED_ENV: copy .env.example"
  if [[ -f .env.example ]]; then
    cp .env.example .env
    log "Created .env from .env.example"
  fi
fi

if [[ -f scripts/setup/load_env.sh ]]; then
  # shellcheck disable=SC1091
  source scripts/setup/load_env.sh
fi

# Pick playbook / modules
if [[ -z "$MODULES" ]]; then
  case "$PLAYBOOK" in
    planning) MODULES="planning" ;;
    finance) MODULES="finance" ;;
    full) MODULES="planning finance knowledge" ;;
    "")
      if [[ -t 0 ]]; then
        echo "Select playbook: 1=planning 2=finance 3=full"
        read -r -p "Choice [1]: " choice
        case "${choice:-1}" in
          2) MODULES="finance" ;;
          3) MODULES="planning finance knowledge" ;;
          *) MODULES="planning" ;;
        esac
      else
        MODULES="planning"
        log "Non-TTY: default modules=planning (use --playbook or --modules)"
      fi
      ;;
    *) die "Unknown playbook: $PLAYBOOK" ;;
  esac
fi

GOLDEN_FLAG=""
case "$MODULES" in
  planning) GOLDEN_FLAG="--golden-planning" ;;
  finance) GOLDEN_FLAG="--golden-finance" ;;
esac

CAP_ARGS=(--only-modules $MODULES)
if [[ "$WRITE_CAP" -eq 1 ]]; then
  CAP_ARGS+=(--write --patch-env)
fi
CAP_ARGS+=("${CONNECTOR_FLAGS[@]}")

log "Phase 3: capabilities profile (modules: $MODULES)"
if [[ "$DRY_RUN" -eq 1 ]]; then
  "$PY" scripts/apply_capabilities_profile.py "${CAP_ARGS[@]}" --dry-run
else
  "$PY" scripts/apply_capabilities_profile.py "${CAP_ARGS[@]}"
  "$PY" scripts/setup/env_tools.py append-hints || true
  "$PY" scripts/setup/env_tools.py status || true
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "Dry-run complete"
  exit 0
fi

log "Phase 4: vault layout + dependencies"
"$PY" scripts/init_vault_layout.py
./scripts/setup.sh
bash scripts/setup_agent_config.sh
"$PY" scripts/setup/materialize_locale.py "$AGENT_LOCALE"
AGENT_LOCALE="$AGENT_LOCALE" bash scripts/ensure_repo_config.sh
if [[ ! -f config/vault_paths.yaml && -f config/vault_paths.yaml.example ]]; then
  cp config/vault_paths.yaml.example config/vault_paths.yaml
fi
"$PY" scripts/setup/env_tools.py set-locale "$AGENT_LOCALE" || true

if [[ "$SKIP_PROMPTS" -eq 0 ]]; then
  log "Phase 5: prompts"
  bash scripts/ensure_bot_prompts.sh
  if [[ ! -f config/agent/onboarding_slots.yaml && -f config/agent/onboarding_slots.yaml.example ]]; then
    cp config/agent/onboarding_slots.yaml.example config/agent/onboarding_slots.yaml
  fi
  "$PY" scripts/scaffold_personalized_prompts.py || true
  "$PY" scripts/seed_planning_prompts.py || true
  bash scripts/ensure_bot_prompts.sh --warn-stubs || true
fi

log "Phase 6: secrets reminder"
"$PY" scripts/setup/env_tools.py list-missing VAULT_PATH DEEPSEEK_API_KEY TELEGRAM_UNIFIED_BOT_TOKEN 2>/dev/null || true
echo "Set secrets: python3 scripts/setup/env_tools.py set VAULT_PATH '/path/to/vault'"
echo "             python3 scripts/setup/env_tools.py set TELEGRAM_UNIFIED_BOT_TOKEN '...'"
echo "             python3 scripts/setup/env_tools.py set DEEPSEEK_API_KEY 'sk-...'"

if [[ "$SKIP_SMOKE" -eq 0 ]]; then
  log "Phase 7: smoke"
  SMOKE_ARGS=(--verify-all)
  if [[ -n "$GOLDEN_FLAG" ]]; then
    SMOKE_ARGS+=("$GOLDEN_FLAG")
  fi
  "$PY" scripts/onboarding_smoke.py "${SMOKE_ARGS[@]}"
fi

log "Done. Start bot: python3 -m unified_bot.main"
log "Optional: ./scripts/install_mac_sync.sh | docs/ONBOARDING.md"
