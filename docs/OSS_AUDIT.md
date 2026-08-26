# OSS universality audit (living doc)

Last review: 2026-08-26 (full canvas F01–F20 close-out).  
North star: one repo, any locale, any module subset, no author identity in git, config-driven everything, setup via onboarding skill + env.

## Canvas close-out (oss-quality-audit)

| ID | Status | Evidence |
|----|--------|----------|
| F01 | ✅ | `load_catalog_config` / messages overlay |
| F02–F03 | ✅ | docs/skills + `setup_agent_config` FULL_INSTALL gate |
| F04 | ✅ | no aeshef-osx; LaunchAgent com.obsidian-agent.* |
| F05 | ✅ | CI `AGENT_LOCALE=en` |
| F06 | ✅ | `shared/config_policy.py` + `tests/test_config_policy.py` |
| F07–F08 | ✅ | locale_merged + shell `:-en` |
| F09 | ✅ | `auto_routing` + `pick_host_domain` removed |
| F10 | ✅ | DOMAIN_* in host dispatch/menus/wire/menu_detection |
| F11 | ✅ | `deploy_mode()` forces single; multi warns |
| F12 | ✅ | composition-root docs + `test_host_import_boundary` |
| F13 | ✅ | `shared/sync` plan + lock; shell evals `run_sync_plan.py`; `kanban_flow.window` carve |
| F14 | ✅ | planning temps from YAML; `test_no_temperature_literals` |
| F15 | ✅ | `knowledge_only` preset + golden |
| F16 | ✅ | `bootstrap_checklist.yaml.example`; README/Docker aligned |
| F17 | ✅ | discovery prefers generic paths |
| F18 | ✅ | CI job `lint` (ruff + shellcheck) |
| F19 | ✅ | planning menu fallthrough → unified |
| F20 | ✅ | `config/domain_messages/{en,ru}/*.yaml.example` packages |

## Config loader contract

See `shared/config_policy.py` (`CONFIG_STEM_LOADERS`).

## Verification

```bash
./scripts/oa-python.sh -m pytest \
  tests/test_config_policy.py \
  tests/test_sync_plan.py \
  tests/test_host_import_boundary.py \
  tests/test_no_temperature_literals.py \
  tests/test_bootstrap_checklist.py \
  tests/test_domain_messages_locale_parity.py \
  tests/test_profile_matrix.py \
  tests/test_telegram_ux_dispatch.py -q
```
