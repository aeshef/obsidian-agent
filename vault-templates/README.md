# Vault layout templates

Folders are **not** duplicated here (locale-specific names live in `config/vault_paths.yaml.example`).

Use the idempotent initializer instead:

```bash
python3 scripts/init_vault_layout.py
```

It reads the active [capabilities profile](../docs/CAPABILITIES.md) and creates only directories for enabled modules.

| Module | Typical folders |
|--------|-----------------|
| finance | `300_*/Данные`, `300_*/Графики/Финансы` |
| planning | `100_*`, `200_*`, `400_*`, `600_*`, action logs under `300_` |
| knowledge | `{knowledge_subdir}/` from `platform.yaml` |

For a fresh machine: set `VAULT_PATH` in `.env`, run `apply_capabilities_profile.py --write`, then `init_vault_layout.py`, then `./scripts/setup.sh`.
