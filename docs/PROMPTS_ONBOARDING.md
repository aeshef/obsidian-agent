# Prompt onboarding

Production prompts are `**/prompts/*.txt` (gitignored). Git ships `*.example.txt` only.

## Tiers

Defined in `config/prompt_manifest.yaml.example` (optional local `prompt_manifest.yaml`):

- **generic_en** — example file contains working English. `scripts/ensure_bot_prompts.sh` may copy it to `.txt` on first install; bot works without immediate edits.
- **personalized** — example is a comment stub. The [obsidian-agent-onboarding](../.cursor/skills/obsidian-agent-onboarding/SKILL.md) skill must fill prod `.txt` from user interview (`user_profile.md`, account names, vault layout).

## Commands

```bash
bash scripts/ensure_bot_prompts.sh
cp config/agent/onboarding_slots.yaml.example config/agent/onboarding_slots.yaml  # once
python3 scripts/scaffold_personalized_prompts.py
bash scripts/ensure_bot_prompts.sh --warn-stubs
python3 -c "from shared.capabilities.prompt_manifest import prompts_missing_prod_text; print(prompts_missing_prod_text())"
```

Personalized prod files start from English scaffolds (`prompt_scaffold_templates.py`); the onboarding skill replaces `{{USER_*}}` slots and edits prompts for the user's accounts and vault.

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
