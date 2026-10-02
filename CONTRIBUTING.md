# Contributing

Thanks for contributing to **obsidian-agent**.

This guide covers the development environment, local setup, testing,
and the workflow for opening a pull request.

**Maintainers:** see [docs/MAINTAINER.md](docs/MAINTAINER.md) for
the public-repository cadence (PR → CI → merge, issue triage).

By participating, you agree to follow our
[Code of Conduct](CODE_OF_CONDUCT.md) (Contributor Covenant 2.1).

---

## Quickstart

This section covers the recommended setup for local development and the
offline checks that can be run without external services.

### Requirements

- Python 3.10+
- Git
- Node.js 22 for dashboard/UI regression checks

### Setup

From the repository root:

```bash
./scripts/setup.sh
cp .env.example .env
./scripts/ensure_bot_venv.sh all
```

The offline test suite uses synthetic fixtures. You do **not** need a Telegram
token, an LLM/API key, a paid API service, or a personal Obsidian vault to run
the automated offline tests.

### Offline checks

The agent harness runs against synthetic fixtures and does not require a live
LLM or external service:

```bash
export PYTHONPATH="$PWD"
finance_bot/.venv/bin/python -m eval.harness.run
```

The Node.js dashboard regression test can be run with:

```bash
node tests/test_echarts_heatmap.cjs
```

A successful harness run reports the number of passed cases, and the ECharts
test reports that the heatmap cells and correlation color scale passed.

### Live setup

Live LLM-backed functionality and external connectors may require additional
configuration or credentials. Follow the relevant connector documentation
before running live integrations.

---

## Fork → branch → test → PR

For a typical contribution:

1. Fork the repository on GitHub.
2. Clone your fork locally.
3. Create a dedicated branch for your change.
4. Make the smallest focused change needed for the issue.
5. Run the relevant tests and checks locally.
6. Review the diff and make sure no secrets or personal configuration are included.
7. Push your branch to your fork.
8. Open a pull request against the upstream `main` branch.

Example:

```bash
git clone https://github.com/<your-username>/obsidian-agent.git
cd obsidian-agent

git switch -c docs/my-contribution

# make your changes

git diff --check
git status
git diff

git add CONTRIBUTING.md
git commit -m "docs: improve contributor quickstart"
git push -u origin docs/my-contribution
```

Keep pull requests scoped to the issue being addressed. Avoid unrelated
refactors or formatting changes.

---

## Окружение

| Шаг        | Команда                                         |
| ---------- | ----------------------------------------------- |
| Python     | 3.10+                                           |
| Установка  | `./scripts/setup.sh`                            |
| `.env`     | `cp .env.example .env`                          |
| venv       | `./scripts/ensure_bot_venv.sh all`              |
| PYTHONPATH | `export PYTHONPATH="$(pwd)"` при ручном запуске |

**Зависимости:** `constraints.txt` — пины для всех venv; `requirements-min.txt` — минимум для CI/smoke; `finance_bot/requirements.txt` (и аналоги) — полный набор домена; `pyproject.toml` — метаданные пакета и dev-tools. Боевые `config/**/*.yaml` в git не коммитятся — только `*.yaml.example`.

### Config loaders (`shared.config_policy` / `shared.yaml_config`)

| API                                      | Use for                                                                                          |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `load_catalog_config`                    | UI / domain string catalogs (`messages`, `domain_messages`): **example as base ⊕ local overlay** |
| `load_locale_merged_config`              | Locale-aware schemas (`kanban_schema`, dashboard templates)                                      |
| `load_runtime_config`                    | Local-only overrides that intentionally replace the whole file (rare)                            |
| `load_merged_config`                     | Additive merge for structured configs                                                            |
| `load_by_policy` / `CONFIG_STEM_LOADERS` | Stem registry — register new stems here; see `tests/test_config_policy.py`                       |

---

## Конфиги и секреты

- **Не коммитьте:** `.env`, боевые промпты, личные yaml, `capabilities.yaml`.
- **Capabilities:** missing YAML = OSS starter unless `OBSIDIAN_AGENT_FULL_INSTALL=1`; present YAML is fail-closed.
- **Core vs connectors:** [docs/CONNECTORS.md](docs/CONNECTORS.md) — first run is modules + LLM only.
- **UI-строки** — `config/messages.*.yaml.example` + local overlay; Default `AGENT_LOCALE=en`.
- **Bot YAML** — в git `*.yaml.example`; pick the loader above by stem.
- **Числа и лимиты** — `config/agent/platform.yaml` / `models.yaml`, не magic numbers в коде.
- **Промпты LLM** — `*.txt` / `config/agent/prompts/`, не строки в `.py`.

### Personal overlay — push checklist

Public `main` is not your life OS. Before every `git push`:

```bash
git status
git diff --cached --name-only
# Must NOT include:
#   .env  config/agent/capabilities.yaml  config/agent/user_profile.md
#   finance_bot/config/badge.yaml  finance_bot/config/broker_sync.yaml
#   **/prompts/*.txt (prod)  *opening_balances*  real vault paths with your name
git check-ignore -v .env config/agent/capabilities.yaml finance_bot/config/badge.yaml
```

Keep author full install via local gitignored files + `OBSIDIAN_AGENT_FULL_INSTALL=1` if needed — not a public `personal` branch.

---

## Checks перед PR

Open a PR against `main` (do not push straight to `main` unless you are the maintainer fixing a broken release and follow [MAINTAINER.md](docs/MAINTAINER.md)).

```bash
SMOKE_INSTALL=1 ./scripts/smoke_imports.sh
export PYTHONPATH="$PWD"
finance_bot/.venv/bin/pip install -q pytest
finance_bot/.venv/bin/python -m pytest \
  tests/test_navigation.py \
  tests/test_agent_platform.py \
  tests/test_note_lookup.py -q
```

CI: `.github/workflows/ci.yml` (Python 3.10–3.12, `AGENT_LOCALE` en + ru).

---

## Good first issues

| Idea                             | Where                                                                                    |
| -------------------------------- | ---------------------------------------------------------------------------------------- |
| New `menu_actions` row + handler | `config/ui_capabilities.yaml.example`, `{bot}/menu_action_handlers.py`                   |
| New connector flag (fail-closed) | `shared/capabilities/profile.py` + preset + CAPABILITIES.md                              |
| EN/RU string parity              | `config/domain_messages/{locale}/*.yaml.example`                                         |
| Shrink a god script further      | `finance_bot/scripts/build_finance_dashboard.py` helpers under `bot/services/dashboard/` |

Open a [capability request](.github/ISSUE_TEMPLATE/capability_request.md) or [locale](.github/ISSUE_TEMPLATE/locale.md) issue if unsure.

---

## Точки входа

| Режим                    | Запуск                                          |
| ------------------------ | ----------------------------------------------- |
| **Prod / рекомендуется** | `python -m unified_bot.main`                    |
| Host package             | `unified_bot.host` (not `shared.telegram.host`) |

---

## Стиль

- Composition root: `unified_bot/host/`; `shared/` is infrastructure (+ `shared/memory` may call domains).
- Скрипты: `scripts/lib/common.sh` + `sync_steps_*.sh`, без хардкода путей VPS.
- Deploy: `./scripts/deploy.sh --prod` для production.

Документация: [docs/README.md](docs/README.md) · [SUPPORT.md](SUPPORT.md) · [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md).
