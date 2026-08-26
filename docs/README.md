# Documentation

User-facing docs for **obsidian-agent** clones and contributors. Maintainer-only notes (`docs/_maintainer/`, `docs/AUDIT_REPO_GOALS*.md`, one-off audits) stay **local** — see root `.gitignore`; they are not on `main`.

| Doc | Purpose |
|-----|---------|
| [SETUP.md](SETUP.md) | First run: venv, `.env`, locale, deploy, Mac sync |
| [ONBOARDING.md](ONBOARDING.md) | Modules, connectors, prompts, smoke tests |
| [CAPABILITIES.md](CAPABILITIES.md) | `capabilities.yaml`, sync steps, UI gates, `menu_actions` |
| [CONNECTORS.md](CONNECTORS.md) | Core vs connectors contract; first-run happy path |
| [MAINTAINER.md](MAINTAINER.md) | Public-repo protocol: PRs, issue triage, community |
| [connectors/HOSTING_WITHOUT_MAC.md](connectors/HOSTING_WITHOUT_MAC.md) | VPS / Linux / Windows without Mac LaunchAgent |
| [connectors/health/FORMAT.md](connectors/health/FORMAT.md) | Portable health KV snapshots (iOS / Android / manual) |
| [connectors/shortcuts/README.md](connectors/shortcuts/README.md) | Shortcut / Tasker recipes (no binary `.shortcut`) |
| [PROMPTS_ONBOARDING.md](PROMPTS_ONBOARDING.md) | Prompt tiers and scaffolds |
| [LOCALE.md](LOCALE.md) | `AGENT_LOCALE` (EN default) |
| [ENV_REFERENCE.md](ENV_REFERENCE.md) | Environment variables |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Monorepo layout, unified_bot, sync |
| [AGENT_PLATFORM.md](AGENT_PLATFORM.md) | Routing, memory, tool loop |
| [AGENT_CONFIG.md](AGENT_CONFIG.md) | `platform.yaml`, agent prompts |
| [TESTING.md](TESTING.md) | pytest and CI |
| [REPO_LAYOUT.md](REPO_LAYOUT.md) | Where to put new files |

Start: [../README.md](../README.md) → [SETUP.md](SETUP.md) → [ONBOARDING.md](ONBOARDING.md).

---

# Документация

Пользовательские доки для клонов и контрибьюторов. Мейнтейнерские заметки (`docs/_maintainer/`, `docs/AUDIT_REPO_GOALS*.md`, разовые аудиты) остаются **локально** — см. `.gitignore`; в публичном `main` их нет.

Таблица выше — те же файлы. Старт: [../README.md](../README.md) → [SETUP.md](SETUP.md) → [ONBOARDING.md](ONBOARDING.md).
