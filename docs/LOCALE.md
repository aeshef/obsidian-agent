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
| `config/domain_messages/{en,ru}/*.yaml.example` | Per-domain packages (**source of truth**) |
| `config/domain_messages.{en,ru}.yaml.example` | Optional local rebuild via `scripts/rebuild_domain_messages.py` (gitignored) |
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
| `dmsg()` | Packages under `config/domain_messages/{locale}/`; optional gitignored overlays `domain_messages.{en,ru}.yaml` |

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
