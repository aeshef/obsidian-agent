# Environment variables / Переменные окружения

## English

Single **`.env`** at repo root (see [`.env.example`](../.env.example)). Required for prod: `VAULT_PATH`, `TELEGRAM_UNIFIED_BOT_TOKEN`, LLM keys (`DEEPSEEK_API_KEY` and/or `OPENROUTER_API_KEY`). Locale: `AGENT_LOCALE=en|ru` (default `en`). Validate: `./scripts/check_env.sh all`. Full tables below (Russian).

---

## Русский

Единый файл: **`.env` в корне монорепо**. Боты также читают `../.env` при запуске из подкаталога.

Шаблон: [`.env.example`](../.env.example). Проверка: `./scripts/check_env.sh all`. С prod: скопируйте недостающие ключи вручную или `scp` с VPS (не коммитьте `.env`).

---

## Обязательный минимум

**Prod (unified):**

| Переменная | Описание |
|------------|----------|
| `VAULT_PATH` | Путь к Obsidian vault |
| `DEEPSEEK_API_KEY` или `DEEPSEEK_API_TOKEN` | LLM (planning, finance, agent) |
| `TELEGRAM_UNIFIED_BOT_TOKEN` | Один бот [@BotFather](https://t.me/BotFather) |
| `DEPLOY_MODE` | `single` (default) |
| `TELEGRAM_USER_ID` | Numeric id владельца (knowledge ingest, алерты) |

**Legacy (`DEPLOY_MODE=multi`):** отдельные `TELEGRAM_PLANNING_BOT_TOKEN`, `TELEGRAM_KNOWLEDGE_BOT_TOKEN`, `TELEGRAM_FINANCE_BOT_TOKEN` или общий `TELEGRAM_BOT_TOKEN`.

---

## Общие

| Переменная | Default / заметка |
|------------|-------------------|
| `TIMEZONE` | UTC; для MSK: `Europe/Moscow` |
| `OBSIDIAN_VAULT_PATH` | алиас `VAULT_PATH` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | `deepseek-chat` |
| `GOALS_YEAR` | текущий год |
| `LOG_LEVEL` | уровень логирования |

---

## Сервер, sync, deploy

| Переменная | Назначение |
|------------|------------|
| `SERVER` | SSH host (обязателен для deploy/sync) |
| `SERVER_VAULT` | vault на VPS |
| `SERVER_BOTS` | `/root/bots` по умолчанию |
| `LOCAL_VAULT` | локальный vault для rsync |
| `AGENT_ROOT` | корень монорепо (auto) |
| `RSYNC_BIN`, `RSYNC_RSH` | rsync / ssh |
| `RSYNC_PUSH_DELETE` | `1` (default): Mac→VPS push deletes VPS orphans; `0` to disable |
| `REMOTE_BOT_DIR`, `REMOTE_DB` | finance pull db |
| `PLANNING_BOT_ROOT` | override planning root |
| `FORCE_*`, `SKIP_*` | флаги obsidian_sync |
| `DEPLOY_VERIFY_WAIT` | секунды verify после deploy |

Gmail IMAP (planning, Mac only): `GMAIL_IMAP_USER`, `GMAIL_IMAP_APP_PASSWORD`, `GMAIL_IMAP_*`.

---

## ASR и embeddings

`ASR_MODEL`, `ASR_LANGUAGE`, `ASR_BASE_URL`, `ASR_API_KEY`, `ASR_ENDPOINT`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OLLAMA_*`, `EMBED_ENDPOINT`.

---

## knowledge_bot

| Переменная | Заметка |
|------------|---------|
| `OPENROUTER_API_KEY` | часть LLM-пайплайна |
| `AGENT_CONFIG_PATH` | default: `knowledge_bot/config` |
| `AUTHOR_CONTEXT`, `ENABLE_WIKILINKS` | контекст и wikilinks |
| `VISION_*`, `YTDLP_*`, `YOUTUBE_*` | медиа pipeline |
| `SERENDIPITY_*`, `KNOWLEDGE_*`, `OPENROUTER_*` | фичи knowledge |
| `API_BILLING_ALERT_*`, `PENDING_LIMIT` | лимиты |

Не задавайте `AGENT_CONFIG_PATH` на несуществующий путь — сломаются sync_hubs/retag.

---

## planning_bot

`PLANNING_BOT_LOG_DIR`, `CHAT_ID_FILE`, `GOALS_CONTEXT_FILE`, `CALENDAR_TZ`, `IPHONE_SYNC_TZ`, `PLANNING_CHAT_*`, `DEADLINE_CHART_HORIZON_DAYS`, `FROM_SYNC`, `SYNC_STATE_DIR`.

---

## finance_bot

`TINKOFF_*`, `BASE_CURRENCY`, `FINANCE_DB_PATH`, `DATABASE_URL`, `FINANCE_USE_VAULT_DB`, `FINANCE_BOT_ROOT`, `FIN_DASHBOARD_START_DATE`, `FIN_ONEOFF_THRESHOLD_RUB`, `FINANCE_REL_*`, `BROKER_SYNC_LABEL_*`, `MPLCONFIGDIR`.

**БД:** запись всегда в **canonical** (`FINANCE_DB_PATH` или `{finance_bot}/finance.db`). Vault `300_Дашборды/Данные/finance.db` — read-only реплика.

`FIN_EXCLUDE_FROM_SPENDING_CATEGORIES` / `FIN_EXCLUDE_FROM_INCOME_CATEGORIES` — что не считать потреблением и «реальным» доходом (переводы, вывод с брокера).

---

## Watchdog

`WATCHDOG_BOT_ROOT`, `WATCHDOG_MODE`, `WATCHDOG_PGREP_PATTERN`, `WATCHDOG_PGREP_FALLBACK`, остальные `WATCHDOG_*` — legacy `scripts/watchdog.sh` (author-only, не в git); production: `deploy.sh --restart-unified`.

---

## Agent platform

| Переменная | Назначение |
|------------|------------|
| `AGENT_DOMAIN` | `finance` / `planning` / `knowledge` — домен процесса (L1 no-op при 3 ботах) |
| `DEPLOY_MODE` | `single` (default, unified_bot) или `multi` (legacy три процесса) |
| `AGENT_MAX_ITERS` | Макс. итераций tool-loop (default 6) |
| `AGENT_SESSION_MAX_TURNS` | Реплик в session memory (default 4 пары) |

Конфиги: см. [AGENT_CONFIG.md](AGENT_CONFIG.md). Шаблоны `config/agent/*.example.yaml`; локально `./scripts/setup_agent_config.sh`. Профиль продукта (модули, коннекторы, sync): [CAPABILITIES.md](CAPABILITIES.md), `CAPABILITIES_PATH`, `CAP_MODULE_*`, `CAP_CONNECTOR_*`, `CAPABILITIES_SYNC_PROFILE`.

| Переменная | Назначение |
|------------|------------|
| `VAULT_REL_KNOWLEDGE` | Подкаталог базы знаний в vault (override `platform.yaml` → `vault.knowledge_subdir`) |
| `AGENT_MAX_ITERS` | override `agent.max_iters` |
| `KNOWLEDGE_*`, `PLANNING_CHAT_*` | override секций в `platform.yaml` |

## Feature flags (заготовка)

В `.env.example` — `FEATURE_*` для будущего `features.yaml`. Полная система флагов пока не подключена.

---

## Поиск в коде

Полный перечень:

```bash
rg "os.environ|getenv" --glob '*.py'
```

См. также: [SETUP.md](SETUP.md), [ARCHITECTURE.md](ARCHITECTURE.md).
