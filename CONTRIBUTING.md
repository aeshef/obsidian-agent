# Contributing

Спасибо, что улучшаете **obsidian-agent**.

---

## Окружение

| Шаг | Команда |
|-----|---------|
| Python | 3.9+ |
| Установка | `./scripts/setup.sh` |
| `.env` | `cp .env.example .env` |
| venv | `./scripts/ensure_bot_venv.sh all` |
| PYTHONPATH | `export PYTHONPATH="$(pwd)"` при ручном запуске |

**Зависимости:** `constraints.txt` — пины для всех venv; `requirements-min.txt` — минимум для CI/smoke; `finance_bot/requirements.txt` (и аналоги) — полный набор домена; `pyproject.toml` — метаданные пакета и dev-tools. Боевые `config/**/*.yaml` в git не коммитятся — только `*.yaml.example`.

### Config loaders (`shared.config_policy` / `shared.yaml_config`)

| API | Use for |
|-----|---------|
| `load_catalog_config` | UI / domain string catalogs (`messages`, `domain_messages`): **example as base ⊕ local overlay** |
| `load_locale_merged_config` | Locale-aware schemas (`kanban_schema`, dashboard templates) |
| `load_runtime_config` | Local-only overrides that intentionally replace the whole file (rare) |
| `load_merged_config` | Additive merge for structured configs |
| `load_by_policy` / `CONFIG_STEM_LOADERS` | Stem registry — register new stems here; see `tests/test_config_policy.py` |

---

## Конфиги и секреты

- **Не коммитьте:** `.env`, боевые промпты, личные yaml, `capabilities.yaml`.
- **Capabilities:** missing YAML = OSS starter unless `OBSIDIAN_AGENT_FULL_INSTALL=1`; present YAML is fail-closed.
- **UI-строки** — `config/messages.*.yaml.example` + local overlay; Default `AGENT_LOCALE=en`.
- **Bot YAML** — в git `*.yaml.example`; pick the loader above by stem.
- **Числа и лимиты** — `config/agent/platform.yaml` / `models.yaml`, не magic numbers в коде.
- **Промпты LLM** — `*.txt` / `config/agent/prompts/`, не строки в `.py`.

---

## Checks перед PR

```bash
SMOKE_INSTALL=1 ./scripts/smoke_imports.sh
export PYTHONPATH="$PWD"
finance_bot/.venv/bin/pip install -q pytest
finance_bot/.venv/bin/python -m pytest \
  tests/test_navigation.py \
  tests/test_agent_platform.py \
  tests/test_note_lookup.py -q
```

CI: `.github/workflows/ci.yml` (Python 3.10–3.12).

---

## Точки входа

| Режим | Запуск |
|-------|--------|
| **Prod / рекомендуется** | `python -m unified_bot.main` |
| Legacy finance | `python -m bot.main` (cwd: finance_bot) |
| Legacy knowledge | `knowledge_bot/start_bot.py` |
| Legacy planning | `python -m planning_bot.app.main` |

---

## Стиль

- Доменная логика в боте; `shared/` — инфраструктура.
- Скрипты: `scripts/lib/common.sh`, без хардкода путей VPS.
- Deploy: `./scripts/deploy.sh --prod` для production.

Документация: [docs/README.md](docs/README.md).
