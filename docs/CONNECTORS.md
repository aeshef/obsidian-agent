# Connectors contract

**Core product** (no connectors required):

```text
Telegram unified_bot + Obsidian vault + OpenAI-compatible LLM
```

Modules (`planning` / `knowledge` / `finance`) turn domains on or off.
**Connectors** are optional pipes into those domains. They are **fail-closed**:
if a connector is off (or omitted from `capabilities.yaml`), it must not appear in:

- reply / inline UI  
- agent tools  
- prompt `@cap` blocks  
- Mac/Linux sync steps (`CAP_SYNC_*`)

See also [CAPABILITIES.md](CAPABILITIES.md) (manifest mechanics) and
[HOSTING_WITHOUT_MAC.md](connectors/HOSTING_WITHOUT_MAC.md).

## First run (happy path)

1. Pick modules only (`planning`, `finance`, `knowledge`, or `full`).
2. Set `VAULT_PATH`, `TELEGRAM_UNIFIED_BOT_TOKEN`, `LLM_API_KEY`.
3. Start the bot.

Do **not** enable broker, meal badge, health, calendar, or Mac context unless
the user asks. Wizard default is core-only; pass explicit `--connectors …` or
`--ask-connectors` for optional prompts.

```bash
./scripts/onboarding_wizard.sh --playbook planning          # core
./scripts/onboarding_wizard.sh --playbook finance --connectors --broker-sync
./scripts/onboarding_wizard.sh --playbook planning --ask-connectors  # TTY y/N each
```

## Connector map

| Connector | Module | Portable default | Notes |
|-----------|--------|------------------|-------|
| `domestic_bank_cards` | finance | often on | Cards/wallets in the ledger UI |
| `manual_broker_accounts` | finance | off | YAML broker accounts, no API |
| `broker_sync` | finance | off | `provider: csv` (any country) or optional `tinkoff` |
| `corporate_badge` | finance | off | Workplace meal benefit; tax/NDFL is config |
| `apple_health` / `health_snapshots` | planning | off | Vault KV files — [health/FORMAT.md](connectors/health/FORMAT.md) |
| `gmail_health_pipeline` | planning | off | Optional email delivery of the same snapshots |
| `apple_calendar` | planning | off | Calendar file in vault |
| `mac_context` | planning | off | Desktop context snapshots (Mac-oriented) |
| `knowledge_serendipity` | knowledge | off | Scheduled random note |

Recipes (Shortcuts / Tasker): [connectors/shortcuts/README.md](connectors/shortcuts/README.md).

## Personal overlay (not in git)

Public `main` must stay free of your life. Keep locally (gitignored):

- `.env`, `config/agent/capabilities.yaml`
- `finance_bot/config/badge.yaml`, `broker_sync.yaml`, opening balances
- prod `**/prompts/*.txt`, `user_profile.md`

Before every `git push`, see [CONTRIBUTING.md](../CONTRIBUTING.md#personal-overlay--push-checklist).

## Rule of thumb

| Put in `main` | Keep private / local |
|---------------|----------------------|
| Connector code + examples | Your enabled flags and tokens |
| Generic docs and samples | Real balances, employers, city paths |
| Fail-closed defaults (off) | Full-install author profile |
