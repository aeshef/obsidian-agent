# Scripts

Скрипты в корне `scripts/` — общие для репозитория (Mac + VPS). Скрипты внутри `finance_bot/scripts/`, `knowledge_bot/scripts/` и т.д. — runtime конкретного бота.

## Первый запуск

| Скрипт | Назначение |
|--------|------------|
| `setup.sh` | venv, `.env`, smoke |
| `setup_agent_config.sh` | `config/agent` из примеров |
| `check_env.sh` | проверка переменных |
| `ensure_bot_venv.sh` | venv по ботам |
| `smoke_imports.sh` | импорты без Telegram |

## Деплой и VPS

| Скрипт | Назначение |
|--------|------------|
| `deploy.sh` | rsync + рестарт (`--prod`, `--restart-unified`, `--patch-agent-env`, …) |
| `install_server_reboot_crontab.sh` | `@reboot` → unified_bot |
| `install_planning_crontab.sh` | cron planning_bot на VPS |
| `server_crontab.example` | пример crontab |

Алиасы **не** дублируем отдельными файлами: используйте `./scripts/deploy.sh --prod`, `--restart-unified`, `--patch-agent-env`.

## Mac: vault sync

| Скрипт | Назначение |
|--------|------------|
| `obsidian_sync.sh` | pull/push vault, дашборды, maintenance |
| `check_sync_health.sh` | маркеры здоровья sync |
| `export_mobile_vault.sh` | iCloud → vault (опционально, `SKIP_MOBILE_VAULT=1`) |
| `install_launchagent.sh` | LaunchAgent для `obsidian_sync` |
| `install_mac_context_launchagent.sh` | LaunchAgent для `Контекст Mac (Obsidian)` каждые 5 мин |

Карта шагов sync: [docs/SETUP.md](../docs/SETUP.md) (§ Mac sync), [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). Корневой `obsidian_sync.sh` — только wrapper для symlink в `~/bin`.

## Промпты / CI

| Скрипт | Назначение |
|--------|------------|
| `ensure_bot_prompts.sh` | `*.example.txt` → `*.txt` + scaffolds; `--check-git`, `--warn-stubs` |
| `scaffold_personalized_prompts.py` | English prod prompts from `prompt_scaffold_templates.py` |
| `seed_planning_prompts.py` | дефолтные planning prompts, если только stub (OSS) |
| `pull_prompts_from_server.sh` | **author-only** (gitignored) — prod prompts с VPS; не нужен клонам |
| `ensure_hubs_registry.sh` | `directory:` → `{knowledge_subdir}/_Хабы` |
| `lib/vault_knowledge_dir.sh` | `vault_knowledge_subdir()` для shell (obsidian_sync) |
| `ensure_tags_prompt.sh` + `.py` | JSON-обёртка `tags.txt` (knowledge) |
| `run_tests.sh` | pytest (вкл. locale parity + prompt guards) |

## Библиотеки

`lib/common.sh`, `lib/deploy_agent.sh`, `lib/bootstrap_python.sh` — подключаются из других скриптов, не вызывайте напрямую без нужды.

One-off / audit scripts: not in git (see root `.gitignore`: `audit_*.py`, `fix_*.py`, …).

`bootstrap_python.sh` — точка входа для venv бота.

## Чего нет в git (намеренно)

- Одноразовые миграции и аудит (`audit_*.py`, `fix_*.py`, `migrate_*.py`, `repair_*.py`, `strip_*.py`) — см. `.gitignore`
- `planning_bot/scripts/_*.py`, `fix_*.py`, `patch_*.py` — локальные правки при выносе i18n
- Legacy multi-bot: `cleanup_server_stale.sh`, `restart_component.sh`, `start_watchdog_detached.sh`, `watchdog.sh`, `finance_bot/scripts/deploy.sh`, per-bot `watchdog.sh` — только локально у автора (`.gitignore`)
- Finance one-off: `import_badge_history.py`, `import_transactions_yaml.py`, `show_recent_txns.py`
- `planning_bot/tools/rename_iphone_snapshots.py`, `rename_action_snapshots.py`, `repair_action_log_format.py`
- `knowledge_bot/tools/vault_audit_report.py`
- `knowledge_bot/config/hubs_registry.yaml` — только `hubs_registry.yaml.example`; боевой файл из `setup.sh` / `ensure_hubs_registry.sh`
- `finance_bot/config/{llm,asr,summary,categories}_*.yaml`, `dashboard_templates.yaml` — только `*.example` в git
- `knowledge_bot/config/duplicate_cleanup.yaml` — только `.example` (author audit tools)
- Scrub history / recover prompts / `merge_env_from_server` — только у автора
