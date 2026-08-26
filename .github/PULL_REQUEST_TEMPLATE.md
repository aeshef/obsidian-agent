## Summary
<!-- 1–3 bullets: why this PR exists -->

## Checklist
- [ ] No secrets / prod prompts / personal `capabilities.yaml` / vault paths
- [ ] New config stems registered in `shared/config_policy.py` (if any)
- [ ] No Cyrillic in `.py` (`tests/test_no_cyrillic_in_py.py`)
- [ ] Locale catalogs: edit packages under `config/domain_messages/{en,ru}/` (no monolith commit)
- [ ] Tests added or updated for the behavior change

## Test plan
- [ ] `./scripts/oa-python.sh -m pytest <relevant tests> -q`
- [ ] (If capabilities) `scripts/onboarding_smoke.py --golden-…`
