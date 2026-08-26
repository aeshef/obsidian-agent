# Setup / Установка

## English

1. `git clone` → `cd obsidian-agent` → `./scripts/setup.sh`
2. Fill `.env`: `VAULT_PATH`, `TELEGRAM_UNIFIED_BOT_TOKEN`, `DEEPSEEK_API_KEY` (default `AGENT_LOCALE=en`)
3. `python -m unified_bot.main` or deploy: `./scripts/deploy.sh --prod`
4. Switch language: `python3 scripts/setup/env_tools.py set-locale ru`

Details: [LOCALE.md](LOCALE.md), [ONBOARDING.md](ONBOARDING.md), [OBSIDIAN_SETUP.md](OBSIDIAN_SETUP.md).

---

## Obsidian (required for dashboards + Templater)

Community plugins and vault templates are **not** optional for planning/knowledge modules. See **[OBSIDIAN_SETUP.md](OBSIDIAN_SETUP.md)**.

Quick path after `setup.sh`:

```bash
python3 scripts/install_obsidian_setup.py --list-plugins   # install these in Obsidian UI
python3 scripts/install_obsidian_setup.py                # copy Templates/ + Templater config
```

---

## Русский

Пошаговая настройка **obsidian-agent** на новой машине. Предполагается macOS для Obsidian + опциональный VPS для 24/7.

По умолчанию в `.env.example` задано `AGENT_LOCALE=en` (английский UI). Русский: `python3 scripts/setup/env_tools.py set-locale ru`.

**Obsidian (плагины + шаблоны):** [OBSIDIAN_SETUP.md](OBSIDIAN_SETUP.md) — без Dataview/Templater/Kanban и `Templates/Clones` система не работает.

---

## 1. Предварительные условия

| Component | Минимум |
|-----------|---------|
| Python | 3.9+ (prod VPS: 3.9.x; локально: 3.12.x) |
| Git | clone репозитория |
| Obsidian vault | Папки из `config/vault_paths.yaml.example` + `init_vault_layout.py` |
| Telegram | Один бот у [@BotFather](https://t.me/BotFather) (`TELEGRAM_UNIFIED_BOT_TOKEN`) или legacy: три токена |
| LLM API | DeepSeek (planning/finance); OpenRouter для knowledge (vision) |

---

## 2. Клонирование и автosetup

```bash
git clone https://github.com/YOUR_GITHUB_USER/obsidian-agent.git
cd obsidian-agent
./scripts/setup.sh
```

Скрипт:

1. Создаёт `.env` из `.env.example`, если файла нет
2. Поднимает venv в каждом боте (`ensure_bot_venv.sh all`)
3. Запускает `check_env.sh`
4. Smoke: `SMOKE_INSTALL=1 smoke_imports.sh` (включая `unified_bot`)
5. Копирует из `*.example`: `messages.ru/en.yaml`, `vault_paths.yaml`, `domain_messages.yaml`, `platform.yaml`, `hubs_registry.yaml`, `nlu_config.yaml`, `media_extensions.yaml` (и др. — см. цикл в `setup.sh`)
6. `./scripts/ensure_bot_prompts.sh` — для каждого `**/config/prompts/*.example.txt` создаёт отсутствующий `*.txt` (не перезаписывает уже заполненный prod)
7. `seed_planning_prompts.py` — planning prompts, если на диске только stub
8. `ensure_hubs_registry.sh` — `directory:` в `knowledge_bot/config/hubs_registry.yaml`
9. `ensure_tags_prompt.sh` — JSON-обёртка для `knowledge_bot/config/prompts/tags.txt`

---

## 3. Заполнение `.env`

**Рекомендуемый минимум (unified):**

```bash
VAULT_PATH=/path/to/your/Obsidian Vault
DEEPSEEK_API_KEY=sk-...
TELEGRAM_UNIFIED_BOT_TOKEN=...
DEPLOY_MODE=single
TELEGRAM_USER_ID=...          # numeric id для knowledge ingest / алертов
```

Legacy (три polling-процесса): **unsupported** — `DEPLOY_MODE` always resolves to `single`.

Узкий профиль продукта (например только финансы): [CAPABILITIES.md](CAPABILITIES.md). Без `capabilities.yaml` — OSS starter; полный продукт только с `OBSIDIAN_AGENT_FULL_INSTALL=1`.

Для sync/deploy:

```bash
SERVER=your-ssh-host
SERVER_BOTS=/root/bots
SERVER_VAULT=/root/obsidian-vault
LOCAL_VAULT=/path/to/local/vault
```

Проверка: `./scripts/check_env.sh all` — [ENV_REFERENCE.md](ENV_REFERENCE.md).

---

## 4. Конфиги (не в git)

| Назначение | Файл из example |
|------------|-----------------|
| UI Telegram | `config/messages.ru.yaml` |
| Лимиты platform | `config/agent/platform.yaml` |
| agent (unified) | `config/agent/prompts/*.txt` |
| knowledge | `knowledge_bot/config/types.yaml` (в git), `prompts/*.txt`, опционально `hubs_registry.yaml` |
| finance | `finance_bot/config/prompts/*.txt`, `llm_config.yaml` и др. из `*.yaml.example` (`load_merged_config`) |
| planning | `planning_bot/config/prompts/*.txt`, `goals_context.md` |
| finance | `nlu_config.yaml`, `broker_sync.yaml`, `initial_accounts.yaml`, `badge.yaml`, … |

Не коммитьте боевые промпты (`*.txt` в `**/prompts/` — в git только `*.example.txt` со stub-комментариями), `badge.yaml`, `subscriptions.yaml`.

Проверка политики: `./scripts/ensure_bot_prompts.sh --check-git` (или `pytest tests/test_prompt_git_policy.py`).

---

## 5. Локальный запуск

```bash
export PYTHONPATH="$(pwd)"
finance_bot/.venv/bin/python -m unified_bot.main
```

Legacy (отладка одного домена): `finance_bot/scripts/run.sh`, `planning_bot/scripts/run.sh`, `knowledge_bot/scripts/run.sh`.

---

## 6. Mac: синхронизация vault

Модульный sync (`capabilities.yaml` + `obsidian_sync.sh`): пути из `vault_paths.yaml`, шаги включаются через capability flags, интервал LaunchAgent — `config/agent/platform.yaml` (`obsidian_sync.launchagent_interval_sec`).

1. SSH-ключ, `SERVER` и `VAULT_PATH` в `.env`
2. `./scripts/install_launchagent.sh`:
   - зеркалирует Agent в `~/Library/Application Support/obsidian-agent/runtime/` (код вне `~/Documents` — обход macOS TCC для фонового launchd);
   - plist: `/bin/zsh`, `WorkingDirectory=$HOME`;
   - label: `LAUNCHAGENT_LABEL` в `.env` (по умолчанию `com.example.obsidian-sync`).
3. После изменений в коде Agent — снова `./scripts/install_launchagent.sh` (обновляет runtime mirror).
4. Если mirror недостаточен: **Полный доступ к диску** для `/bin/zsh` (после обновления macOS права часто сбрасываются).

Ручной прогон (из vault, как в dev): `~/bin/obsidian_sync.sh` — лог `/tmp/obsidian_sync_debug.log`.

---

## 7. VPS: деплой

Пошагово для новичков: **`docs/DEPLOY_VPS.md`** (минимальные ресурсы, SSH-ключ, `SERVER` в `.env`).

```bash
./scripts/deploy.sh --prod --install-deps
```

`--prod`: patch `.env` на сервере, rsync кода, рестарт **только** `unified_bot`, verify процесса.

Дополнительно:

```bash
./scripts/install_server_reboot_crontab.sh
./scripts/install_planning_crontab.sh
./scripts/ensure_tags_prompt.sh --remote
```

Legacy watchdog: `./scripts/deploy.sh --prod --legacy-bots`.

---

## 8. Проверка

```bash
SMOKE_INSTALL=1 ./scripts/smoke_imports.sh
export PYTHONPATH="$(pwd)"
finance_bot/.venv/bin/python -m pytest tests/test_navigation.py tests/test_agent_platform.py -q
```

На сервере: `tail -f ${SERVER_BOTS}/logs/unified_bot.log`

---

## 9. Типичные проблемы

| Симптом | Что проверить |
|---------|---------------|
| `VAULT_PATH не задан` | `.env` и экспорт перед запуском |
| `ModuleNotFoundError: shared` | `PYTHONPATH` = корень монорепо |
| Пустые подписи кнопок | `config/messages.ru.yaml` из example |
| knowledge retag | `./scripts/ensure_tags_prompt.sh` |

---

## 10. Mac ↔ VPS sync (optional)

If you use `SERVER` in `.env`:

```bash
./scripts/install_mac_sync.sh   # LaunchAgent → obsidian_sync.sh
```

- Push Mac→VPS uses `rsync --delete` by default (`RSYNC_PUSH_DELETE=1`) so files removed on Mac disappear on the server; server-only paths stay protected via rsync excludes in `obsidian_sync.sh`.
- `.sync/last_sync_ok.txt` updates only on success; failures write `.sync/last_sync_failed.txt`.
- Calendar: events older than 3 months roll into `Календарь.json` → `archive.monthly`; huge `Календарь.txt` may be compacted (see `planning_bot/config/calendar_retention.yaml.example`).

Health: `./scripts/check_sync_health.sh`, log: `/tmp/obsidian_sync_debug.log`.

---

## Дальше

- [ONBOARDING.md](ONBOARDING.md)
- [CAPABILITIES.md](CAPABILITIES.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
