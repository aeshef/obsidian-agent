# Locale (English-first)

## Toggle

```bash
# Default for new clones (in .env.example)
AGENT_LOCALE=en

# Switch anytime
python3 scripts/setup/env_tools.py set-locale en
python3 scripts/setup/env_tools.py set-locale ru
```

`set-locale` sets `AGENT_LOCALE` and runs `scripts/setup/materialize_locale.py` (messages, domain_messages, `vault_paths.yaml`, finance category lists when local files are missing).

## What is in git

| File | Role |
|------|------|
| `config/messages.en.yaml.example` | **Canonical** Telegram UI keys (English) |
| `config/messages.ru.yaml.example` | Russian UI (same keys, pytest parity) |
| `config/domain_messages/{en,ru}/*.yaml.example` | Per-domain packages (source of truth); monolith regenerated via `scripts/rebuild_domain_messages.py` |
| `config/domain_messages.en.yaml.example` | Generated English catalog (compat) |
| `config/domain_messages.ru.yaml.example` | Generated Russian catalog (compat) |
| `config/vault_paths.en.yaml.example` | English vault folder/file names (default) |
| `config/vault_paths.ru.yaml.example` | Russian vault paths |
| `finance_bot/config/categories_mvp.{en,ru}.yaml.example` | Expense categories by locale |
| `finance_bot/config/income_categories.{en,ru}.yaml.example` | Income categories by locale |

Add new **Telegram** keys to `messages.en.yaml.example` first, then mirror Russian.

Add new **tool** keys to both domain catalogs (or run `scripts/setup/translate_domain_messages.py` after editing RU).

## Runtime

| API | Locale |
|-----|--------|
| `msg()` / `msgf()` | `messages.en` or `messages.ru` |
| `dmsg()` | RU: gitignored `domain_messages.ru.yaml` overlays `.ru.example` (local wins, missing keys fill from example). EN: `domain_messages.en` merged over that RU catalog |

Default `AGENT_LOCALE` is **`en`** (`shared/locale.py`).

## Prompts

Agent routers ship as **generic_en** (`*.example.txt` with working English). Personalized prompts are comment stubs — fill during onboarding in your language.

## Maintainer: full English domain catalog

```bash
# OPENROUTER_API_KEY or DEEPSEEK_API_KEY in .env
python3 scripts/setup/translate_domain_messages.py --provider openrouter
pytest tests/test_domain_messages_locale_parity.py -q
```

Until EN leaves are translated, `AGENT_LOCALE=en` may show Russian tool text from the RU catalog (merge fallback).
