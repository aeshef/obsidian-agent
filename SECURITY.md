# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `main` / latest tag | Yes |
| Older commits | Best-effort only |

**Runtime:** Python 3.10–3.12 recommended (3.9 may work; CI covers 3.10–3.12).  
**Hosts:** Linux VPS for `unified_bot`; macOS for optional `obsidian_sync` LaunchAgent.

## What this project handles

- Telegram bot tokens and LLM API keys in **local `.env`** (never commit)
- Optional vault path on disk / VPS; treat the vault as **sensitive personal data**
- Capability flags that fail closed: omitted modules/connectors stay **off**

## Reporting a vulnerability

Please **do not** open a public GitHub issue for secrets leakage or RCE-class bugs.

1. Email or DM the maintainer listed on the GitHub profile / SECURITY contact if published.
2. Include: affected commit/tag, reproduction without real tokens when possible, impact.
3. Allow reasonable time for a fix before public disclosure.

If you accidentally committed secrets: rotate tokens immediately, then open an issue describing the rotation (not the secret).

## Hardening checklist (operators)

- [ ] `.env` and `capabilities.yaml` gitignored and not in backups that are public
- [ ] Prod prompts (`**/prompts/*.txt`) and `user_profile.md` stay local
- [ ] VPS SSH keys limited; `deploy.sh` does not overwrite author `vault_paths.yaml`
- [ ] `OBSIDIAN_AGENT_FULL_INSTALL=1` only on maintainer machines that intentionally omit `capabilities.yaml`
- [ ] Review connector playbooks before enabling broker / mail / device sync

## Threat model (short)

| Asset | Risk | Mitigation |
|-------|------|------------|
| Bot token | Impersonation / spam | Env-only; rotate on leak |
| Vault markdown | PII exposure | Private VPS/disk; no public mirror of vault |
| LLM API key | Bill / data to vendor | Env-only; minimize payloads in prompts |
| Capability bypass | Unexpected domain tools | Fail-closed YAML; CI golden presets |
