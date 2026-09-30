#!/usr/bin/env bash
# One-shot onboarding wizard over obsidian-agent-onboarding skill phases.
# Non-interactive setup steps; secrets still require env_tools or /setup in Cursor.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONIOENCODING=utf-8
# Prefer .env / author machine locale; EN is OSS default for fresh clones only.
if [[ -f .env ]]; then
  _loc="$(grep -E '^AGENT_LOCALE=' .env | tail -1 | cut -d= -f2- | tr -d "\"'" | xargs)"
  [[ -n "$_loc" ]] && AGENT_LOCALE="$_loc"
fi
AGENT_LOCALE="${AGENT_LOCALE:-en}"

PLAYBOOK=""
MODULES=""
CONNECTOR_FLAGS=()
ASK_CONNECTORS=0
DRY_RUN=0
SKIP_PROMPTS=0
SKIP_SMOKE=0
WRITE_CAP=1
FAST=0

usage() {
  cat <<'EOF'
Usage: scripts/onboarding_wizard.sh [options]

Guided OSS setup (skill: .cursor/skills/obsidian-agent-onboarding/SKILL.md).
Stranger target: <30 min with --fast (intro defaults) + /setup for secrets/finalize.

Options:
  --playbook planning|finance|knowledge|full   Golden path (default: prompt if TTY)
  --modules "planning finance"         Space-separated modules (overrides playbook modules)
  --connectors FLAGS                 Extra apply_capabilities_profile flags (repeatable)
  --ask-connectors                   TTY: offer optional connectors (default: skip — core only)
  --locale en|ru                     Default: en
  --fast                             Apply intro interview defaults (skip personal Q&A)
  --dry-run                          apply_capabilities_profile --dry-run only
  --skip-prompts                     Skip ensure_bot_prompts / scaffold
  --skip-smoke                       Skip onboarding_smoke.py
  --no-write-cap                     Do not write capabilities.yaml (author full install)
  -h, --help                         This help

Examples:
  ./scripts/onboarding_wizard.sh --playbook planning --fast
  ./scripts/onboarding_wizard.sh --playbook finance --connectors --broker-sync
  ./scripts/onboarding_wizard.sh --playbook planning --ask-connectors
  ./scripts/onboarding_wizard.sh --playbook knowledge

Secrets: wizard prompts on TTY, or set via ./scripts/oa-python.sh scripts/setup/env_tools.py set KEY 'value'
Status:  ./scripts/oa-python.sh scripts/onboarding_status.py
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --playbook) PLAYBOOK="${2:-}"; shift 2 ;;
    --modules) MODULES="${2:-}"; shift 2 ;;
    --connectors) CONNECTOR_FLAGS+=("${2:-}"); shift 2 ;;
    --ask-connectors) ASK_CONNECTORS=1; shift ;;
    --locale) AGENT_LOCALE="${2:-}"; shift 2 ;;
    --fast) FAST=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-prompts) SKIP_PROMPTS=1; shift ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    --no-write-cap) WRITE_CAP=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

oa_py() {
  if [[ -x "$ROOT/scripts/oa-python.sh" ]]; then
    "$ROOT/scripts/oa-python.sh" "$@"
  else
    python3 "$@"
  fi
}

_prompt_secret() {
  local key="$1" hint="$2"
  local cur=""
  if [[ -f .env ]]; then
    cur="$(grep -E "^${key}=" .env | tail -1 | cut -d= -f2- | tr -d "\"'" | xargs)"
  fi
  if [[ -n "${cur:-}" && "$cur" != *sk-...* && "$cur" != *YOUR* && "$cur" != *changeme* && "$cur" != *replace* ]]; then
    log "$key already set"
    return 0
  fi
  if [[ ! -t 0 ]]; then
    log "NEED_ENV: $key ($hint)"
    return 0
  fi
  echo "$hint"
  if [[ "$key" == *KEY* || "$key" == *TOKEN* ]]; then
    read -r -s -p "$key: " val
    echo
  else
    read -r -p "$key: " val
  fi
  if [[ -n "${val:-}" ]]; then
    oa_py scripts/setup/env_tools.py set "$key" "$val"
  fi
}

# Phase 0 — detect
log "Phase 0: detect context"
if [[ -f config/agent/capabilities.yaml ]]; then
  echo "capabilities.yaml: present"
else
  echo "capabilities.yaml: absent (OSS starter until --write)"
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
    knowledge) MODULES="knowledge" ;;
    full) MODULES="planning finance knowledge" ;;
    "")
      if [[ -t 0 ]]; then
        echo "Select playbook: 1=planning (~15m) 2=finance (~20m) 3=knowledge 4=full"
        read -r -p "Choice [1]: " choice
        case "${choice:-1}" in
          2) MODULES="finance" ;;
          3) MODULES="knowledge" ;;
          4) MODULES="planning finance knowledge" ;;
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

# Optional connectors — off by default (docs/CONNECTORS.md). Pass --ask-connectors or --connectors …
if [[ "$ASK_CONNECTORS" -eq 1 && -t 0 && ${#CONNECTOR_FLAGS[@]} -eq 0 ]]; then
  log "Optional connectors (Enter = No for each)"
  _ask_conn() {
    local flag="$1" prompt="$2"
    read -r -p "$prompt [y/N]: " ans
    case "${ans:-}" in y|Y|yes|YES) CONNECTOR_FLAGS+=("$flag") ;; esac
  }
  case "$MODULES" in
    *finance*)
      _ask_conn --broker-sync "Enable broker portfolio sync (CSV file or optional T-Invest API)?"
      _ask_conn --corporate-badge "Enable corporate meal badge?"
      ;;
  esac
  case "$MODULES" in
    *planning*)
      _ask_conn --apple-health "Enable health snapshots (phone file / Shortcuts)?"
      _ask_conn --gmail-health-pipeline "Enable Gmail health email pipeline?"
      _ask_conn --apple-calendar "Enable calendar export into vault?"
      _ask_conn --mac-context "Enable Mac context snapshots?"
      ;;
  esac
  case "$MODULES" in
    *knowledge*)
      _ask_conn --knowledge-serendipity "Enable knowledge serendipity?"
      ;;
  esac
elif [[ ${#CONNECTOR_FLAGS[@]} -eq 0 ]]; then
  log "Core only — connectors off (use --ask-connectors or --connectors FLAG)"
fi

GOLDEN_FLAGS=()
case "$MODULES" in *planning*) GOLDEN_FLAGS+=(--golden-planning) ;; esac
case "$MODULES" in *finance*) GOLDEN_FLAGS+=(--golden-finance) ;; esac
case "$MODULES" in *knowledge*) GOLDEN_FLAGS+=(--golden-knowledge) ;; esac

case "$MODULES" in
  planning) CAP_ARGS=(--preset planning_only) ;;
  finance) CAP_ARGS=(--preset finance_only) ;;
  knowledge) CAP_ARGS=(--preset knowledge_only) ;;
  "planning finance knowledge") CAP_ARGS=(--preset full) ;;
  *)
    read -r -a _mods <<< "$MODULES"
    CAP_ARGS=(--only-modules "${_mods[@]}")
    ;;
esac
if [[ "$WRITE_CAP" -eq 1 ]]; then
  CAP_ARGS+=(--write --patch-env)
fi
CAP_ARGS+=("${CONNECTOR_FLAGS[@]}")

log "Phase 1: bootstrap minimal venv (PyYAML for oa-python.sh)"
if [[ ! -x finance_bot/.venv/bin/python ]]; then
  ./scripts/setup.sh
else
  log "finance_bot/.venv already present"
fi

log "Phase 2: VAULT_PATH (required before init_vault_layout)"
_prompt_secret VAULT_PATH "Absolute path to your Obsidian vault folder"

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "Phase 3 (dry-run): capabilities profile (modules: $MODULES)"
  oa_py scripts/apply_capabilities_profile.py "${CAP_ARGS[@]}" --dry-run
  log "Dry-run complete"
  exit 0
fi

log "Phase 3: capabilities profile (modules: $MODULES)"
oa_py scripts/apply_capabilities_profile.py "${CAP_ARGS[@]}"
oa_py scripts/setup/env_tools.py append-hints || true
oa_py scripts/setup/env_tools.py status || true

log "Phase 4: locale + repo config"
oa_py scripts/setup/env_tools.py set-locale "$AGENT_LOCALE" --refresh-vault-paths || true
oa_py scripts/setup/materialize_locale.py "$AGENT_LOCALE" --refresh-vault-paths
AGENT_LOCALE="$AGENT_LOCALE" bash scripts/ensure_repo_config.sh

if [[ ! -f config/agent/capabilities.yaml ]]; then
  die "capabilities.yaml missing — run apply_capabilities_profile --write first"
fi

log "Phase 5: interview scaffold"
if [[ ! -f config/agent/onboarding_slots.yaml && -f config/agent/onboarding_slots.yaml.example ]]; then
  cp config/agent/onboarding_slots.yaml.example config/agent/onboarding_slots.yaml
fi
if [[ ! -f config/agent/onboarding_state.yaml && -f config/agent/onboarding_state.yaml.example ]]; then
  cp config/agent/onboarding_state.yaml.example config/agent/onboarding_state.yaml
fi
if [[ "$FAST" -eq 1 ]]; then
  oa_py scripts/onboarding_interview.py apply-intro-defaults --locale "$AGENT_LOCALE"
else
  oa_py scripts/onboarding_interview.py list --phase intro || true
  echo "Run /setup in Cursor for live interview, or: oa-python.sh scripts/onboarding_interview.py answer ID 'text'"
fi

log "Phase 6: vault layout + dependencies"
oa_py scripts/init_vault_layout.py
./scripts/setup.sh
bash scripts/setup_agent_config.sh

if [[ "$SKIP_PROMPTS" -eq 0 ]]; then
  log "Phase 7: prompts"
  bash scripts/ensure_bot_prompts.sh
  if [[ ! -f config/agent/onboarding_slots.yaml && -f config/agent/onboarding_slots.yaml.example ]]; then
    cp config/agent/onboarding_slots.yaml.example config/agent/onboarding_slots.yaml
  fi
  oa_py scripts/scaffold_personalized_prompts.py || true
  if [[ "$MODULES" == *planning* ]]; then
    oa_py scripts/seed_planning_prompts.py || true
  fi
  bash scripts/ensure_bot_prompts.sh --warn-stubs || true
fi

log "Phase 8: secrets"
_prompt_secret TELEGRAM_UNIFIED_BOT_TOKEN "BotFather → /newbot → paste token"
_prompt_secret LLM_API_KEY "OpenAI-compatible key (DeepSeek / OpenRouter / Groq / local) — also accepts DEEPSEEK_API_KEY"
case "$MODULES" in
  *knowledge*) _prompt_secret OPENROUTER_API_KEY "https://openrouter.ai (vision/KB) — needed before KB ingest" ;;
esac
oa_py scripts/setup/env_tools.py list-missing VAULT_PATH LLM_API_KEY TELEGRAM_UNIFIED_BOT_TOKEN 2>/dev/null || true

log "OS checklist (you do these — not automated)"
echo "  - Obsidian: enable community plugins from vault .obsidian/community-plugins.json"
echo "  - macOS Full Disk Access if Mac sync / Health Shortcuts"
echo "  - Status: ./scripts/oa-python.sh scripts/onboarding_status.py"

if [[ "$MODULES" == *finance* ]]; then
  log "Phase 8b: finance initial accounts (after telegram_id in /setup interview)"
  if [[ -f finance_bot/config/initial_accounts.yaml ]]; then
    oa_py finance_bot/scripts/apply_initial_accounts.py --dry-run 2>/dev/null || true
  fi
fi

if [[ "$SKIP_SMOKE" -eq 0 ]]; then
  log "Phase 9: smoke"
  SMOKE_ARGS=(--verify-all)
  SMOKE_ARGS+=("${GOLDEN_FLAGS[@]}")
  oa_py scripts/onboarding_smoke.py "${SMOKE_ARGS[@]}"
fi

log "Phase 10: status"
oa_py scripts/onboarding_status.py || true
log "Done. Finish in Cursor: /setup → after_secrets interview → run bot → confirm-bot → finalize deploy"
log "Start bot: ./scripts/run_unified_bot.sh"
