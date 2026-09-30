# Support

## Quick links

| Need | Where |
|------|--------|
| **First install (<30 min)** | [docs/ONBOARDING_STRANGER.md](docs/ONBOARDING_STRANGER.md) or Cursor `/setup` |
| **Bug** | [Bug report](.github/ISSUE_TEMPLATE/bug_report.md) issue template |
| **New connector / module idea** | [Capability request](.github/ISSUE_TEMPLATE/capability_request.md) |
| **EN/RU string** | [Locale issue](.github/ISSUE_TEMPLATE/locale.md) |
| **How-to / architecture question** | [GitHub Discussions](https://github.com/aeshef/obsidian-agent/discussions) |
| **Security (tokens, RCE)** | [SECURITY.md](SECURITY.md) — **no public issues** |
| **Contribute** | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Before opening an issue

```bash
./scripts/oa-python.sh scripts/onboarding_status.py   # progress + blockers
./scripts/oa-python.sh scripts/onboarding_smoke.py --verify-all --golden-planning  # adjust flags
```

Redact tokens and vault paths. Do not paste `.env`, prod prompts, or `capabilities.yaml`.

## Good first issues

Labeled tasks for newcomers: [good first issue](https://github.com/aeshef/obsidian-agent/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
