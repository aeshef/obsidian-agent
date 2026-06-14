# Obsidian setup

Dashboards, kanban, knowledge ingest, and Templater scripts depend on a small set of **Community plugins** and vault assets shipped in this repo under `vault-templates/obsidian/`.

## English

### 1. Install Obsidian

Desktop app (macOS recommended for sync agent). Open your vault folder (`VAULT_PATH` from `.env`).

### 2. Community plugins (required)

Settings → Community plugins → turn on **Restricted mode: off**, then install and enable:

| Plugin ID | Purpose |
|-----------|---------|
| `dataview` | Dashboard `dataviewjs` blocks (progress, goals, routines) |
| `templater-obsidian` | Hotkey templates: add task to kanban, create KB entities |
| `obsidian-kanban` | Kanban board `100_*/📋 …` (path from `vault_paths.yaml`) |

List from CLI:

```bash
python3 scripts/install_obsidian_setup.py --list-plugins
```

Optional: `obsidian-tasks-plugin`, `3d-graph`, `3d-graph-new` (graph view only).

Plugins are **not** bundled in git (Obsidian Store). You install them once per vault; mobile mirror copies plugin folders via `export_mobile_vault.sh`.

### 3. Install vault assets from repo

After `./scripts/setup.sh` or onboarding (with `VAULT_PATH` set):

```bash
python3 scripts/init_vault_layout.py          # dirs + dashboards + obsidian assets
python3 scripts/install_obsidian_setup.py     # templates only
python3 scripts/install_obsidian_setup.py --force   # overwrite Templater / clones
```

Copies into vault (paths from `config/vault_paths.yaml`):

| Repo | Vault destination |
|------|-------------------|
| `vault-templates/obsidian/clones/*.j2.md` | `{automation}/Templates/Clones/` — knowledge bot Jinja templates (`types.yaml`) |
| `vault-templates/obsidian/entities/ru/` | `{automation}/Templates/Сущности/` (RU) or `Templates/Entities/` (EN) |
| `vault-templates/templater/add_task.md.template` | `{automation}/Templates/v2/Добавить_Задачу.md` or `Add_Task.md` |
| `vault-templates/obsidian/snippets/*.css` | `.obsidian/snippets/` (deadline highlight, tags) |
| `vault-templates/obsidian/config/community-plugins.json` | `.obsidian/community-plugins.json` (if missing) |
| `vault-templates/obsidian/config/templater-data.json.template` | `.obsidian/plugins/templater-obsidian/data.json` |

`{automation}` = `800_Автоматизация` (RU) or `800_Automation` (EN) — see `vault_paths`.

### 4. Templater settings (manual check)

Settings → Templater:

- **Template folder location** must match `templates_v2` in `vault_paths` (install script writes `data.json`).
- Enable **Trigger Templater on new file creation** if you use folder templates.
- Assign a hotkey: Templater → insert `Добавить_Задачу` / `Add_Task` (planning module).

Add-task script is **generated** from `kanban_schema.yaml` + `obsidian_setup.{locale}.yaml` (no hardcoded paths in repo Python).

### 5. Dataview

No extra config. Reload vault after dashboard scaffold (`scaffold_vault_dashboards.py`).

### 6. Verify

1. Open `📊 Прогресс_{year}` — category table should include archive + active kanban.
2. Run Templater → Add task — new line in backlog column with `#goal/` / `#priority/` tags.
3. Knowledge: `types.yaml` template names must exist under `Templates/Clones/`.

---

## Русский

### 1. Установи Obsidian

Десктоп (macOS — для LaunchAgent sync). Открой vault (`VAULT_PATH` в `.env`).

### 2. Community plugins (обязательные)

Настройки → Community plugins → **Restricted mode: выкл**, установи:

| Plugin ID | Зачем |
|-----------|--------|
| `dataview` | Блоки `dataviewjs` на дашбордах |
| `templater-obsidian` | Шаблоны: добавить задачу, создать сущность KB |
| `obsidian-kanban` | Канбан `100_Задачи/📋 Доска_Задач.md` |

Список: `python3 scripts/install_obsidian_setup.py --list-plugins`

Опционально: `obsidian-tasks-plugin`, `3d-graph`.

### 3. Установка шаблонов из репозитория

```bash
python3 scripts/init_vault_layout.py
python3 scripts/install_obsidian_setup.py
python3 scripts/install_obsidian_setup.py --force   # перезаписать шаблоны
```

Шаблоны **в git** (`vault-templates/obsidian/`), в vault копируются скриптом — не правь только на одной машине без `--force` и sync.

### 4. Templater

- Папка шаблонов: `800_Автоматизация/Templates/v2` (прописывается в `data.json` скриптом).
- Hotkey на `Добавить_Задачу.md`.

### 5. Проверка

- Дашборд прогресса — категории с архивом.
- Templater → задача в бэклог.
- Clones на месте для knowledge bot.

---

## Config files

| File | Role |
|------|------|
| `config/obsidian_setup.{en,ru}.yaml.example` | Plugin list, Templater UI strings |
| `config/vault_paths.yaml` | Folder names, `templater_add_task_md`, `templates_*` paths |
| `planning_bot/config/kanban_schema.yaml` | Columns, tags for add-task template |

See also: [SETUP.md](SETUP.md), [vault-templates/README.md](../vault-templates/README.md).
