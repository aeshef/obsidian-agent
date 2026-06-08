# Prompt onboarding

Production prompts are `**/prompts/*.txt` (gitignored). Git ships `*.example.txt` only.

## Tiers

Defined in `config/prompt_manifest.yaml.example` (optional local `prompt_manifest.yaml`):

- **generic_en** — example file contains working English. `scripts/ensure_bot_prompts.sh` may copy it to `.txt` on first install; bot works without immediate edits.
- **personalized** — example is a comment stub. The [obsidian-agent-onboarding](../.cursor/skills/obsidian-agent-onboarding/SKILL.md) skill must fill prod `.txt` from user interview (`user_profile.md`, account names, vault layout).

## Commands

```bash
python3 scripts/onboarding_interview.py answer user_about '...'   # /setup interview
python3 scripts/onboarding_interview.py answer finance_accounts 'Card, Cash'
bash scripts/ensure_bot_prompts.sh
python3 scripts/scaffold_personalized_prompts.py
bash scripts/ensure_bot_prompts.sh --warn-stubs
python3 scripts/onboarding_smoke.py --complete
```

Slots live in `config/agent/onboarding_slots.yaml` (from interview). Personalized prod files start from scaffolds (`prompt_scaffold_templates.py`); `/setup` fills `{{USER_*}}` and should refine tone in prod `*.txt` for the user's locale.

## Capability blocks

In prod `.txt`:

```text
<!-- @cap planning -->
...
<!-- @/cap -->
```

Filtered by `shared/capabilities/prompt_filter.py` when the connector is off.

## Tests

- `tests/test_prompt_examples_are_stubs.py` — tier policy
- `tests/test_prompt_git_policy.py` — no prod `*.txt` in git; personalized stubs only
- `tests/test_prompt_scaffolds.py` — onboarding scaffolds
- `tests/test_prompt_preamble.py` — dynamic supplement

Author full install: do not overwrite existing prod prompts.
