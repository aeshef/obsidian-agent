# OSS universality audit (living doc)

Last review: 2026-08-26 (OSS quality audit fix-all).  
North star: one repo, any locale, any module subset, no author identity in git, config-driven everything, setup via onboarding skill + env.

## Philosophy scorecard

| Principle | Status | Evidence / gap |
|-----------|--------|----------------|
| **Unified host** | ✅ | `unified_bot` + `shared/telegram/host`; free text → `answer_unified` |
| **Modular bots** | ✅ | `capabilities.yaml` fail-closed; presets incl. `knowledge_only` |
| **Agent NL loop** | ✅ | Menus → declarative dispatch; non-menu planning → unified fallthrough |
| **No Cyrillic in `.py`** | ✅ | `tests/test_no_cyrillic_in_py.py` |
| **Text in YAML** | ✅ | catalogs via `load_catalog_config` (example ⊕ overlay) |
| **Numbers in YAML** | ✅ | planning temps from `platform.yaml`; dashboard insight temp nested |
| **Paths in YAML** | ✅ | `vault_paths.{en,ru}`; discovery prefers generic Agent paths |
| **Prompts in files** | ✅ | `*.example.txt` in git; prod gitignored |
| **Default locale EN** | ✅ | `AGENT_LOCALE=en` in CI, shell `:-en`, run_tests |
| **No personal data in git** | ✅ | LaunchAgent `com.obsidian-agent.*`; no `aeshef-osx` defaults |
| **Simple setup** | ✅ | starter unless `OBSIDIAN_AGENT_FULL_INSTALL=1`; skill + docs aligned |

## Config loader contract

| API | Stems |
|-----|--------|
| `load_catalog_config` | `messages`, `domain_messages` |
| `load_locale_merged_config` | `kanban_schema`, dashboard templates |
| `load_merged_config` | `ui_capabilities`, additive structured YAML |
| `load_runtime_config` | rare full replace |

## Done (2026-08-26 OSS fix-all)

| Area | Change |
|------|--------|
| Catalog overlay | `i18n.messages` → `load_catalog_config`; EN domain_messages overlay |
| Capabilities | `setup_agent_config` gates on FULL_INSTALL; docs/skills omit≠full |
| Identity | mac-host defaults; LaunchAgent label; no Cyrillic path probe in export |
| CI / shell | `AGENT_LOCALE=en`; shell `:-en` |
| Host | removed `auto_routing.py`; `message_proxy`; DOMAIN_* + planning fallthrough |
| Modules | `knowledge_only` preset + sync profile + golden smoke |
| Locale merge | kanban/dashboard prefer locale example base |

## Deferred (large / intentional)

| Item | Why |
|------|-----|
| Move host under `unified_bot/` | Composition documented; full move is a follow-up PR |
| Split `obsidian_sync.sh` / god modules | Carve later; out of trust-blocker scope |
| Split giant `domain_messages` | Parity tests keep drift in check |
| Drop `DEPLOY_MODE=multi` code | Quarantined in docs/examples; tests still cover |

## Verification

```bash
AGENT_LOCALE=en ./scripts/setup.sh
./scripts/oa-python.sh -m pytest \
  tests/test_runtime_config.py \
  tests/test_profile_matrix.py \
  tests/test_capabilities.py \
  tests/test_auto_routing.py \
  tests/test_telegram_ux_dispatch.py \
  tests/test_no_cyrillic_in_py.py -q
./scripts/oa-python.sh scripts/onboarding_smoke.py \
  --golden-planning --golden-finance --golden-knowledge --agent-sanity
```
