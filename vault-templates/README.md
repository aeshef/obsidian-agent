# Vault templates

## Folders

Locale-specific folder names live in `config/vault_paths.{en,ru}.yaml.example` → `config/vault_paths.yaml`.

```bash
./scripts/oa-python.sh scripts/init_vault_layout.py
```

Creates directories for enabled modules only ([capabilities profile](../docs/CAPABILITIES.md)).

## Dashboards (`dashboards/`)

Obsidian dashboard markdown is **scaffolded** from:

- `config/vault_dashboards.{en,ru}.yaml.example` — block catalog + UI strings
- `vault-templates/dashboards/*.md.template` — dataviewjs fragments
- `planning_bot/config/kanban_schema.yaml` — tag prefixes, categories
- `config/vault_paths.yaml` — file and folder names

```bash
./scripts/oa-python.sh scripts/scaffold_vault_dashboards.py
./scripts/oa-python.sh scripts/scaffold_vault_dashboards.py --force  # overwrite
```

`init_vault_layout.py` runs scaffold automatically (skips existing files).

Finance dashboard body is built by `finance_bot/scripts/build_finance_dashboard.py` from `dashboard_templates.yaml`.

## Routines (`routines/`)

Routines/signals statistics markdown is scaffolded from:

- `config/vault_routines.{en,ru}.yaml.example` — page catalog + UI strings
- `vault-templates/routines/*.md.template` — dataviewjs fragments
- `config/vault_paths.yaml` — folder and file names (`routines` block)
- `planning_bot/config/routines.yaml` — section header message keys

```bash
./scripts/oa-python.sh scripts/scaffold_vault_routines.py
./scripts/oa-python.sh scripts/scaffold_vault_routines.py --force
```

Live routine status is stored in `Данные/routines_today.json` (bot-only). Task list: `📅 Рутины/📋 Конфиг_Задач.md`. Signals override: `📊 Сигналы/📋 Конфиг_Сигналов.yaml`.

`init_vault_layout.py` and bot startup run `ensure_routines_layout()` (migrate legacy paths, scaffold stats).
