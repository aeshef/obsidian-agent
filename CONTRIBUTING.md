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

**Зависимости:** `constraints.txt` — пины для всех venv; `requirements-min.txt` — минимум для CI/smoke; `finance_bot/requirements.txt` (и аналоги) — полный набор домена; `pyproject.toml` — метаданные пакета и dev-tools. Боевые `config/**/*.yaml` в git не коммитятся — только `*.yaml.example`, runtime читает example или локальный override (`shared.yaml_config.load_merged_config`).

---

## Конфиги и секреты

- **Не коммитьте:** `.env`, боевые промпты, личные yaml.
- **UI-строки** — `config/messages.en.yaml` (canonical keys) + `messages.ru.yaml` (в git только `*.example`), не в Python. Default `AGENT_LOCALE=en`.
- **Bot YAML** — в git `*.yaml.example`; runtime через `load_merged_config` / локальный override.
- **Числа и лимиты** — `config/agent/platform.yaml`, не magic numbers в коде.
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
