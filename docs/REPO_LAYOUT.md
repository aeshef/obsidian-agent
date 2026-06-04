# Repository layout

Where files belong in **obsidian-agent**. Use this when adding code or wondering if something is misplaced.

## Target tree

```text
obsidian-agent/
├── README.md, README.en.md, LICENSE, CONTRIBUTING.md
├── .env.example, constraints.txt, requirements-min.txt
├── pyproject.toml, pytest.ini
├── obsidian_sync.sh          # thin wrapper → scripts/obsidian_sync.sh (for ~/bin symlinks)
├── assets/                   # README banner, architecture.svg
├── config/                   # repo-wide YAML (not per-bot secrets)
│   ├── agent/                # platform: capabilities, prompts, routing, tools
│   ├── messages.{en,ru}.yaml.example
│   ├── vault_paths.{en,ru}.yaml.example
│   └── domain_messages.{en,ru}.yaml.example
├── docs/                     # user-facing docs only (tracked in git)
├── scripts/                  # monorepo ops: deploy, sync, setup, CI helpers
│   ├── lib/                  # shell libraries (source, do not run directly)
│   └── setup/                # onboarding: env_tools, load_env, update_shellrc
├── shared/                   # infra + agent platform (no domain business rules)
├── unified_bot/              # production entry: main.py only
├── finance_bot/              # finance domain
├── knowledge_bot/            # knowledge domain
├── planning_bot/             # planning domain
├── tests/                    # pytest
├── launchd/                  # macOS LaunchAgent *.example.plist
├── vault-templates/          # pointer doc; real layout via init_vault_layout.py
└── .cursor/skills/           # guided OSS onboarding
```

## Per-package rules

| Package | Put here | Do not put here |
|---------|----------|-----------------|
| **shared/** | LLM, paths, i18n, agent core, telegram host, capabilities | Finance/kanban handlers, prompts text |
| **unified_bot/** | `main.py`, host wiring | Domain tools, configs |
| **{bot}/bot/** or **{bot}/app/** | aiogram handlers, models, schedulers | Repo-wide scripts |
| **{bot}/config/** | `*.yaml.example` + `prompts/*.example.txt` | Committed `*.yaml` / `prompts/*.txt` (gitignored); loaders merge example + local |
| **{bot}/services/** | Domain logic used by handlers/tools | One-off audit CLIs |
| **{bot}/i18n/** | Domain string helpers (`knowledge_bot/i18n/domain_text.py`) | Random `.py` at package root |
| **{bot}/core/** | Shared bot config/helpers (`planning_bot/core/vault_discover.py`) | Scripts-only modules |
| **{bot}/tools/** | CLIs called from **obsidian_sync** or cron | Ad-hoc analyze/fix scripts (author-only, gitignored) |
| **{bot}/scripts/** | `run.sh`, watchdog, cron wrappers, chart builders invoked by sync | Duplicate of `scripts/` at repo root |
| **scripts/** | Cross-bot: deploy, sync, capabilities, onboarding smoke | Bot-specific runtime |

## Prompts (three layers — intentional)

| Location | Role |
|----------|------|
| `config/agent/prompts/` | Unified agent: host_query, routers, health_tools, … |
| `finance_bot/config/prompts/` | Finance NLU / analyst (personalized) |
| `planning_bot/config/prompts/` | Planning conversation / kanban |
| `knowledge_bot/config/prompts/` | KB extract / tags / query |

Prod `*.txt` is always gitignored; only `*.example.txt` in git.

## Mac sync entrypoints

| File | Role |
|------|------|
| `obsidian_sync.sh` (repo root) | Symlink target: sets `AGENT_ROOT`, execs `scripts/obsidian_sync.sh` |
| `scripts/obsidian_sync.sh` | Full sync implementation |
| `scripts/export_mobile_vault.sh`, `check_sync_health.sh` | Optional Mac helpers |

## Author-only (on disk, not in public git)

Maintainer batch tools and notes may exist locally under:

- `knowledge_bot/tools/analyze_*.py`, `reprocess_notes.py`, …
- Maintainer notes: `docs/_maintainer/`, `docs/OPS.md`, … (see root `.gitignore`, not on GitHub `main`)
- `scripts/archive/`, `planning_bot/scripts/backfill_*.py` (candidates to gitignore)

Clones only need `knowledge_bot/tools/vault_daily_maintenance.py` for KB sync step.

`knowledge_bot/config/hubs_registry.yaml` is gitignored (copy from `hubs_registry.yaml.example` in `setup.sh`).

## Adding something new

1. **Used by one bot only** → `{bot}/services/` or `{bot}/app/agent_tools.py`.
2. **Called from obsidian_sync / VPS cron** → `{bot}/tools/` or `{bot}/scripts/` and document in `scripts/README.md`.
3. **Two+ bots, not agent** → `shared/{domain}/`.
4. **Deploy / env / capabilities** → `scripts/` + `shared/capabilities/`.
5. **User-facing doc** → `docs/` (short index in `docs/README.md`).

See also [ARCHITECTURE.md](ARCHITECTURE.md) and [AGENT_PLATFORM.md](AGENT_PLATFORM.md).
