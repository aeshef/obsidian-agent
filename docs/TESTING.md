# Testing / Тесты

## English

CI (`.github/workflows/ci.yml`): `py_compile`, `smoke_imports.sh`, `run_tests.sh`, plus capabilities job (`test_messages_locale_parity`, `test_domain_messages_locale_parity`, prompt guards). Not every file under `tests/` runs in CI — see table below. Local: `bash scripts/run_tests.sh tests/test_foo.py -q`.

---

## Русский

## CI (GitHub Actions)

Workflow `.github/workflows/ci.yml` на каждый push/PR:

1. `py_compile` всех модулей (Python 3.10–3.12)
2. `scripts/smoke_imports.sh` — venv + импорты ботов
3. `bash scripts/run_tests.sh` — стабильный набор finance/planning/shared + `test_note_complete` (knowledge venv)
4. Job **capabilities** — presets, onboarding smoke, guard-тесты:
   - `test_messages_locale_parity` — EN/RU ключи, без кириллицы в EN
   - `test_prompt_git_policy` — prod prompts не в git
   - `test_prompt_scaffolds` — шаблоны onboarding

**Не все ~57 файлов в `tests/` в default CI** — намеренно.

| Модуль | Почему не в CI |
|--------|----------------|
| `test_kanban_agent.py` | Падает, если в env задан `KANBAN_AGENT_WRITES=1` |
| `test_nlu_batch_parse.py` | 1 кейс расходится с текущим парсером |
| `test_note_review.py` | Нужен knowledge venv + jinja2 (в CI только `test_note_complete`) |
| `test_ocr_profile.py` | optional easyocr |
| `test_telegram_media_helpers.py` | тяжёлые зависимости / collection error в finance venv |
| `test_health_data.py`, `test_bulk_ingest_mode.py`, … | интеграционные / ручной прогон |

Локально прогнать один файл:

```bash
bash scripts/run_tests.sh tests/test_agent_platform.py -q
```

Все модули по очереди:

```bash
for f in tests/test_*.py; do finance_bot/.venv/bin/python -m pytest "$f" -q || echo FAIL "$f"; done
```

## Добавление в CI

Критерий: проходит на чистом Ubuntu после `smoke_imports.sh`, без секретов vault, без opt-in env.
