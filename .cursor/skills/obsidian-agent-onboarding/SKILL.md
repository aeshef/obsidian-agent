---
name: obsidian-agent-onboarding
description: >-
  Guided OSS setup for obsidian-agent: modules, connectors, atomic .env API,
  prod prompts, golden playbooks (planning-only / finance-only). Triggers:
  install, onboard, configure, first clone, fill prompts, env_tools, load-env.
disable-model-invocation: false
---
# obsidian-agent onboarding (guided)

You are the **onboarding operator**. The user cloned git and has mostly `*.example` stubs — turn this into a **working, non-leaking** install. You run shell/Python steps yourself; the user only pastes secrets when asked.

## Non‑negotiable rules

| Rule | Why |
|------|-----|
| Repo root = directory with `unified_bot/`, `scripts/setup.sh`, `config/agent/` | |
| **Never** commit `.env`, `capabilities.yaml`, `badge.yaml`, prod `**/prompts/*.txt`, `user_profile.md` | Secrets + personal tone |
| **Author full install**: if `config/agent/capabilities.yaml` is **absent**, do **not** create it (absent = all modules/connectors on) | Preserves maintainer machine |
| **New clone**: always `--write` capabilities profile for the chosen modules | Explicit contract |
| **Never overwrite** existing prod `*.txt` or `user_profile.md` unless user explicitly asks | `ensure_bot_prompts.sh` only copies missing |
| `.env`: append placeholders via `--patch-env` / `env_tools.py append-hints`; secrets via `env_tools.py set` only | Never replace non-empty values without `--force` |
| Use **AskQuestion** for modules/connectors; **do not mention** declined options in UI/prompts/sync | Capability contract |
| After each shell step: show **exit code + stderr**; stop on failure unless user wants to skip | |
| UI strings: `config/messages.en.yaml` (canonical keys) + `messages.ru.yaml` — **no Cyrillic in `.py`** | |
| Default `AGENT_LOCALE=en`; Russian: `env_tools.py set-locale ru` | |

## Shell conventions (every phase)

```bash
cd "$AGENT_ROOT"   # clone root
export PYTHONIOENCODING=utf-8
# load-env
source scripts/setup/load_env.sh
```

Optional once per machine: `python3 scripts/setup/update_shellrc.py` → user can run `oa-load-env` later.

## Python API for `.env` (preferred for secrets)

User pastes a token in chat → you write it atomically (no echoing the value back):

```bash
python3 scripts/setup/env_tools.py set VAULT_PATH '/absolute/path/to/vault'
python3 scripts/setup/env_tools.py set TELEGRAM_UNIFIED_BOT_TOKEN '...'
python3 scripts/setup/env_tools.py set DEEPSEEK_API_KEY 'sk-...'
python3 scripts/setup/env_tools.py append-hints          # after capabilities.yaml exists
python3 scripts/setup/env_tools.py status
python3 scripts/setup/env_tools.py list-missing VAULT_PATH DEEPSEEK_API_KEY
```

Same hints as `python3 scripts/apply_capabilities_profile.py ... --patch-env` (`shared/setup/env_patch.py`).

## Golden playbooks (fast paths)

Use **AskQuestion** once to pick a playbook, then **do not ask** about items in the “never ask” column.

### Planning-only (~15 min)

| Step | Command / action |
|------|------------------|
| Profile | `python3 scripts/apply_capabilities_profile.py --only-modules planning --write --patch-env` |
| Core env | `env_tools.py set` → `VAULT_PATH`, `TELEGRAM_UNIFIED_BOT_TOKEN` (or `TELEGRAM_BOT_TOKEN`), `DEEPSEEK_API_KEY` |
| Layout | `python3 scripts/init_vault_layout.py` → `./scripts/setup.sh` → `bash scripts/setup_agent_config.sh` |
| Prompts | `bash scripts/ensure_bot_prompts.sh` — personalize planning `*.txt` only |
| Smoke | `python3 scripts/onboarding_smoke.py --verify-all --golden-planning` |

**Never ask (unless user volunteers):** finance module, broker API, corporate badge, knowledge/ingest, `OPENROUTER` for KB, Mac sync VPS details, nutrition/KBJU charts, Gmail health pipeline, broker_sync.yaml.

**Optional connectors** (only if user asks): `--apple-health`, `--gmail-health-pipeline`, `--apple-calendar`, `--mac-context`.

### Finance-only (~20 min)

| Step | Command / action |
|------|------------------|
| Profile | `python3 scripts/apply_capabilities_profile.py --only-modules finance --write --patch-env` |
| Core env | `VAULT_PATH`, Telegram token, `DEEPSEEK_API_KEY` |
| Finance config | `cp finance_bot/config/broker_sync.yaml.example` only if user wants **API** broker later; default preset uses manual accounts + cards |
| Prompts | Finance personalized prompts (`nlu_prompt`, `query_prompt`, …) — **no broker brand names in prompt logic**; localized labels live in `messages.ru.yaml` |
| Smoke | `python3 scripts/onboarding_smoke.py --verify-all --golden-finance` |

**Never ask (unless user volunteers):** planning kanban/cron, health Shortcuts, badge, Gmail IMAP, calendar export, Mac context snapshots, knowledge serendipity, `install_planning_crontab.sh`.

**Optional:** `--broker-sync` + `broker_sync.yaml` + `env_tools.py set TINKOFF_API_TOKEN` (tinkoff provider); `--corporate-badge` + `badge.yaml`.

### Full / custom

Ask modules separately, then connectors per enabled module (see Phase 2). Do not assume finance-only or planning-only.

---

## Flow (mermaid)

```mermaid
flowchart TD
  A[Detect: capabilities + VAULT_PATH] --> B[AskQuestion: playbook or modules]
  B --> C[Ask connectors for enabled modules only]
  C --> D[apply_capabilities_profile --write --patch-env]
  D --> E[env_tools append-hints + set secrets]
  E --> F[init_vault_layout + setup.sh]
  F --> G[ensure_bot_prompts + fill prompts]
  G --> H[onboarding_smoke --verify-all --golden-*]
  H --> I{Mac sync?}
  I -->|yes| J[install_mac_sync.sh]
  I -->|no| K[unified_bot.main smoke]
```

---

## Phase 0 — Detect context

```bash
test -f config/agent/capabilities.yaml && echo HAS_CAP || echo FULL_INSTALL_DEFAULT
test -f .env && grep -E '^VAULT_PATH=' .env || echo NEED_ENV
python3 scripts/setup/env_tools.py list-missing VAULT_PATH 2>/dev/null || true
```

- No `.env` → `cp .env.example .env`; `env_tools.py set VAULT_PATH` with user path.
- `FULL_INSTALL_DEFAULT` on **your** machine (user says they are the author) → skip writing `capabilities.yaml`.
- Any other clone → proceed with `--write` profile.

---

## Phase 1 — Modules (AskQuestion)

| User need | CLI |
|-----------|-----|
| Kanban / tasks / goals / routines | `--only-modules planning` |
| Money / expenses | `--only-modules finance` |
| Notes / KB | `--only-modules knowledge` |
| Mix | `--only-modules planning finance` (space-separated) |

Or apply a golden playbook from the table above (skip redundant module questions).

---

## Phase 2 — Connectors (enabled modules only)

One **AskQuestion** cluster at a time. Flags: `python3 scripts/apply_capabilities_profile.py --help` and `shared/capabilities/onboarding_catalog.py`.

| Connector | CLI flags | Secret / file |
|-----------|-----------|---------------|
| Yandex meal badge | `--corporate-badge` `--setup-badge` | `config/badge.yaml` |
| Broker API | `--broker-sync` | `broker_sync.yaml`, `TINKOFF_API_TOKEN` (tinkoff) |
| Manual accounts / cards | on with finance; `--no-domestic-bank-cards` to hide | bot UI |
| Apple Health | `--apple-health` | `health_parse.yaml`, Shortcuts |
| Gmail → health | `--gmail-health-pipeline` | `GMAIL_IMAP_*` via `env_tools.py set` |
| Body / nutrition charts | features in capabilities YAML | |
| Apple Calendar | `--apple-calendar` | vault calendar file |
| Mac focus snapshots | `--mac-context` | vault `actions/Mac/` |
| KB serendipity | `--knowledge-serendipity` | knowledge module |

**Declined connector** → omit from prompts (`@cap`), UI (`ui_capabilities.yaml`), and do not require its env keys in smoke.

---

## Phase 3 — Apply profile + env hints

```bash
python3 scripts/apply_capabilities_profile.py \
  --only-modules MODULE_LIST \
  CONNECTOR_FLAGS... \
  --dry-run

python3 scripts/apply_capabilities_profile.py \
  --only-modules MODULE_LIST \
  CONNECTOR_FLAGS... \
  --write --patch-env

python3 scripts/setup/env_tools.py append-hints
python3 scripts/setup/env_tools.py status
```

`sync.profile` defaults to **auto** (planning-only → `planning_kanban`, finance-only → `finance_only`).

---

## Phase 4 — Vault layout + dependencies

```bash
python3 scripts/init_vault_layout.py
./scripts/setup.sh
bash scripts/setup_agent_config.sh
cp config/vault_paths.yaml.example config/vault_paths.yaml   # if missing; tune folder names
python3 scripts/setup/env_tools.py set-locale en   # or ru — materializes messages.*.yaml
```

Ensure `.env` contains `AGENT_PROMPT_DYNAMIC_SUPPLEMENT=0` (see `.env.example`) — prefer explicit `<!-- @cap -->` blocks in prod prompts.

---

## Phase 5 — Prompts

```bash
bash scripts/ensure_bot_prompts.sh
cp config/agent/onboarding_slots.yaml.example config/agent/onboarding_slots.yaml  # if missing
python3 scripts/scaffold_personalized_prompts.py
bash scripts/ensure_bot_prompts.sh --warn-stubs
```

| Tier | Your job |
|------|----------|
| **generic_en** | Copy-safe from `*.example.txt`; wrap optional blocks in `<!-- @cap id -->` … `<!-- @/cap -->` |
| **personalized** | Interview user; fill prod `*.txt` from `onboarding_slots.yaml` |

**`@cap` aliases:** `planning`, `finance`, `broker`, `badge`, `gmail`, `calendar`, `health`, `body_metrics`, `nutrition`, `mac_context`, `knowledge`, `domestic_cards`.

Example prod blocks (see `health_tools.example.txt`, `context_tools.example.txt`):

```text
<!-- @cap health -->
…health tool instructions…
<!-- @/cap -->
```

**Never** `cp` over existing prod `.txt`.

---

## Phase 6 — Secrets (user pastes → you `env_tools.py set`)

Workflow per cluster:

1. Send the user a **link + variable name** (never log the secret).
2. User pastes value → `python3 scripts/setup/env_tools.py set KEY 'value'`.
3. `python3 scripts/onboarding_smoke.py --verify-all` (add `--require-env` when all clusters done).

| Secret | Where to get it | Env key |
|--------|-----------------|---------|
| Telegram bot | [BotFather](https://t.me/BotFather) | `TELEGRAM_UNIFIED_BOT_TOKEN` or `TELEGRAM_BOT_TOKEN` |
| LLM | [DeepSeek](https://platform.deepseek.com/) | `DEEPSEEK_API_KEY` |
| Vision / KB | [OpenRouter](https://openrouter.ai/) | `OPENROUTER_API_KEY` |
| Gmail IMAP | Google App Passwords | `GMAIL_IMAP_USER`, `GMAIL_IMAP_APP_PASSWORD` |
| Broker (tinkoff) | Provider developer portal | `TINKOFF_API_TOKEN` + `broker_sync.yaml` |

---

## Phase 7 — Smoke gates

```bash
python3 scripts/onboarding_smoke.py --verify-all --golden-planning   # planning playbook
python3 scripts/onboarding_smoke.py --verify-all --golden-finance    # finance playbook
python3 scripts/onboarding_smoke.py --verify-all --require-env --agent-sanity  # full done
PYTHONPATH=. python3 -m pytest tests/test_profile_matrix.py tests/test_ui_bindings.py \
  tests/test_agent_sanity.py tests/test_prompt_examples_are_stubs.py \
  tests/test_prompt_preamble.py tests/test_no_cyrillic_in_py.py -q
./scripts/run_tests.sh
```

CI runs `--golden-planning --golden-finance` without live Telegram.

---

## Phase 8 — Mac sync / VPS (optional)

```bash
./scripts/install_mac_sync.sh
```

`obsidian_sync.sh` reads `VAULT_FOLDER_*` from `config/vault_paths.yaml` (same as Python). Planning cron on server:

```bash
./scripts/install_planning_crontab.sh   # no-op when CAP_MODULE_PLANNING=0
```

---

## Phase 9 — Run bot

```bash
python3 -m unified_bot.main
```

User sends `/start` → one message per enabled module.

---

## Checklist

- [ ] `VAULT_PATH` set via `env_tools.py set`
- [ ] `capabilities.yaml` written (except author full install)
- [ ] `env_tools.py append-hints` + all required secrets set
- [ ] No stub prod prompts for **enabled** personalized files
- [ ] `onboarding_smoke.py --verify-all` + golden flag for playbook
- [ ] pytest capability + no-cyrillic green
- [ ] Manual Telegram smoke per module

---

## Reference

- [scripts/setup/README.md](../../../scripts/setup/README.md) — `env_tools.py`, `load_env.sh`, `update_shellrc.py`
- [docs/ONBOARDING.md](../../../docs/ONBOARDING.md)
- [docs/CAPABILITIES.md](../../../docs/CAPABILITIES.md)
- [docs/PROMPTS_ONBOARDING.md](../../../docs/PROMPTS_ONBOARDING.md)
- [docs/LOCALE.md](../../../docs/LOCALE.md)
- `python3 scripts/apply_capabilities_profile.py --help`
