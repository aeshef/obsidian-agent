# Onboarding setup helpers

Used by `.cursor/skills/obsidian-agent-onboarding/SKILL.md`. All commands run from **repo root**.

## Conventions

| Prefix | Meaning |
|--------|---------|
| `# load-env` | `source scripts/setup/load_env.sh` — export vars from `.env` for the next shell steps |
| `PYTHONIOENCODING=utf-8` | Prefix every `python3` call that reads/writes UTF-8 text |

Optional: persist helpers in the user shell rc (idempotent):

```bash
python3 scripts/setup/update_shellrc.py
# then: oa-load-env   # calls load_env.sh with AGENT_ROOT set
```

## Python API (preferred)

```bash
# Append missing keys only (never overwrites values)
python3 scripts/setup/env_tools.py append-hints

# User pasted a token — you set it (refuse overwrite unless --force)
python3 scripts/setup/env_tools.py set TELEGRAM_UNIFIED_BOT_TOKEN '123:ABC...'
python3 scripts/setup/env_tools.py set DEEPSEEK_API_KEY 'sk-...'

# What is still empty for enabled connectors
python3 scripts/setup/env_tools.py status
python3 scripts/setup/env_tools.py list-missing VAULT_PATH DEEPSEEK_API_KEY
```

Equivalent to `apply_capabilities_profile.py --patch-env` (same `shared/setup/env_patch.py`).

### UI language

```bash
python3 scripts/setup/env_tools.py set-locale en   # default for OSS clones
python3 scripts/setup/env_tools.py set-locale ru
python3 scripts/setup/materialize_locale.py en
```

See [docs/LOCALE.md](../../docs/LOCALE.md).

Regenerate full English `domain_messages.en.yaml.example` (maintainer, needs `OPENROUTER_API_KEY` or `DEEPSEEK_API_KEY`):

```bash
python3 scripts/setup/translate_domain_messages.py --provider openrouter --batch-size 40
```

## Apply capabilities + env in one step

```bash
python3 scripts/apply_capabilities_profile.py --only-modules planning --write --patch-env
```
