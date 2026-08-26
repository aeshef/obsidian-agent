# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `scripts/onboarding_status.py` — single readiness checklist
- Public retrieval gold `eval/gold/public_v0.yaml` + demo storyboard
- Interactive wizard: knowledge playbook, connector asks, TTY secrets

### Changed
- Finance dashboard CLI thin (`scripts/…` → `bot.services.dashboard.build`)
- Interview CLI: no fuzzy skip NLP; `--choice` / `--mvp` for /setup skill
- `full` preset: modules on, connectors off until asked
- `setup.sh` scopes venvs/configs by capabilities

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
