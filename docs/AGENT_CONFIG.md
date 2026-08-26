# Agent platform config

## English

Git ships **templates only** (`config/agent/*.example.yaml`, `prompts/*.example.txt`). Run `./scripts/setup_agent_config.sh` to copy local `platform.yaml`, routing, tools, and prompts (gitignored). Tune `VAULT_REL_KNOWLEDGE` and vault layout in `.env` / `platform.yaml`. Russian section below.

---

## Русский

Публичный репозиторий хранит только **шаблоны** (`*.example.yaml`, `*.example.txt`). Локальные и prod-файлы не коммитятся.

## Быстрый старт

```bash
./scripts/setup_agent_config.sh
```

Создаёт при отсутствии:

- `config/agent/platform.yaml`
- `config/agent/{memory,models,routing,tools}.yaml`
- `config/agent/prompts/*.txt`
- `config/agent/user_profile.md`

**Не создаёт** `capabilities.yaml` без флага (см. `setup_agent_config.sh`: starter, или omit + `OBSIDIAN_AGENT_FULL_INSTALL=1` = full). Иначе: `apply_capabilities_profile.py --write` — [CAPABILITIES.md](CAPABILITIES.md).

## Приоритет настроек

1. Переменные окружения (см. `.env.example`, `docs/ENV_REFERENCE.md`)
2. `config/agent/platform.yaml` — лимиты, таймауты, `vault.knowledge_subdir`, `vault.knowledge_index_extra_folders`
3. Значения из `*.example.yaml` (если локальный файл не создан)

## Ключевые файлы

| Шаблон | Назначение |
|--------|------------|
| `platform.yaml.example` | Лимиты RAG, action-log, agent loop, LLM classify |
| `routing.yaml.example` | `general_domain` при `domain: general` |
| `models.yaml.example` | Роли → модель / temperature |
| `tools.yaml.example` | Краткий `domain_hint` для tool-select |
| `memory.yaml.example` | Профиль и инсайты |
| `prompts/*.example.txt` | Роутеры домена, интентов, tool-select |

## Vault

Каталог базы знаний внутри `VAULT_PATH`:

- `platform.yaml` → `vault.knowledge_subdir` (write root + primary index root; дефолт в шаблоне: `Knowledge`)
- env: `VAULT_REL_KNOWLEDGE`
- `platform.yaml` → `vault.knowledge_index_extra_folders` — доп. корни индекса (ключи из `vault_paths.folders`, напр. `handwritten`); read/search only, без agent writes

Остальные топ-уровневые папки vault — в `shared/paths.py` (`VaultPaths`); при необходимости вынесите их в тот же `platform.yaml` в форке.

## Deploy

После `rsync config/agent` на сервер выполните на VPS (или добавьте в deploy):

```bash
cd /root/bots && bash scripts/setup_agent_config.sh
```

И задайте в `.env` свои `VAULT_REL_KNOWLEDGE` и пути vault.
