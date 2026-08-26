# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` (DeepSeek env names remain aliases)
- Portable health snapshot spec + samples (`docs/connectors/health/`)
- Shortcut / Tasker recipes (`docs/connectors/shortcuts/`)
- Hosting without Mac + systemd unit example
- Broker provider `csv` (balance file sync)
- OSS-neutral finance defaults: `BASE_CURRENCY=USD`, `TIMEZONE=UTC`, broker `provider: none|csv` first; Tinkoff optional
- Meal badge example without NDFL; `show_ndfl_estimate` defaults off
- EN/RU UI strings: generic “broker” / account names (no bank brands)
- Capabilities YAML alias `health_snapshots` → `apple_health`

### Changed
- Vision uses `OPENROUTER_BASE_URL` / `VISION_BASE_URL` (no hardcoded host)
- README / onboarding: Mac optional; LLM provider-agnostic

## [0.1.0] - 2026-08-26

### Added
- Unified Telegram host over planning / knowledge / finance
- Fail-closed `capabilities.yaml` (OSS starter vs `OBSIDIAN_AGENT_FULL_INSTALL`)
- EN + RU example catalogs, vault paths, prompts scaffolds
- Single bootstrap contract: `config/agent/bootstrap_checklist.yaml.example`
- `knowledge_only` capabilities preset + golden smoke
- Config stem registry (`shared/config_policy.py`)
- Sync step libs: `sync_steps_rsync.sh`, `sync_steps_charts.sh`, `sync_steps_maintenance.sh`
- Host composition root under `unified_bot/host/`
- Packages: `planning_bot.services.kanban_flow`, `planning_bot.services.action_log`
- Domain message packages under `config/domain_messages/{en,ru}/`
- Mac `obsidian_sync` + VPS deploy scripts
- Guided `/setup` skill and CLI onboarding wizard
- CI: Python 3.10–3.12, `AGENT_LOCALE` en+ru, ruff + shellcheck
- `CHANGELOG.md`, `SECURITY.md`, GitHub issue/PR templates

### Changed
- Catalog configs use example ⊕ local overlay (`load_catalog_config`)
- Default `AGENT_LOCALE=en` in CI and shell fallbacks
- `DEPLOY_MODE=multi` unsupported (forced to `single`)
- Docker documented as runtime **after** bootstrap, not a shortcut
- README: one Quick start checklist; `requires-python >= 3.10`

### Removed
- Dead `auto_routing` / `pick_host_domain` free-text path
- Compat shims under `shared/telegram/host/` (import `unified_bot.host`)

[Unreleased]: https://github.com/aeshef/obsidian-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aeshef/obsidian-agent/releases/tag/v0.1.0
