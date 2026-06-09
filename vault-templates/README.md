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
