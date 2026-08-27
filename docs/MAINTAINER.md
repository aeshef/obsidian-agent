# Maintainer protocol (public repo)

`main` is public. Treat every commit as something a stranger can clone, grep, and
quote. This is the working agreement for the primary maintainer and for Cursor
agents acting on this repo.

## Default: PR → CI → merge

| Change | Path |
|--------|------|
| Features, refactors, docs that land on `main` | Branch → **Pull Request** → green CI → merge |
| Community PRs | Review within a few days; thank first, then nit |
| Hotfix (CI red / security) | Still prefer a PR; if you must push `main` directly, open a follow-up issue |

Do **not** push straight to `main` for routine work anymore. Agents must open a
PR unless the user explicitly says «push to main» for an emergency.

```bash
git checkout -b fix/short-topic
# …commit…
git push -u origin HEAD
gh pr create --title "…" --body "…"
# wait for CI
gh pr merge --squash   # preferred for linear history
```

### PR hygiene (maintainer)

- Title: imperative, OSS-safe (`Fix preamble broker gate`, not personal vault talk).
- Body: use `.github/PULL_REQUEST_TEMPLATE.md`.
- Diff scan: no `.env`, prod prompts, `capabilities.yaml`, real names, employer, balances.
- Prefer **squash merge** so `main` stays readable.

## Issues — triage loop

Open issues are the product backlog visitors see. Cadence:

1. **Ack within ~48h** — even «looking into this» / label only.
2. **Label** — `bug` / `enhancement` / `question` / `good first issue` / `needs-info`.
3. **Scope** — reject or redirect anything that needs personal overlay (real tokens, private prompts).
4. **Close with care** — link the PR or explain why wontfix; never ghost.

Seed `good first issue` tasks stay open until a PR references them (`Fixes #N`).

### What not to do in public replies

- Do not paste personal vault paths, bank names, or prod prompt snippets.
- Do not promise private 1:1 debugging with secrets in the thread — move to email only if needed, still scrub.

## Community PRs

1. Run CI; skim for secrets and hard-coded personal locale.
2. Prefer small follow-ups on `main` over blocking newcomers on style nits.
3. After merge: comment thanks + link docs if they missed a related page.
4. Close related issues with `Fixes #…` when applicable.

## Branch protection (recommended)

In GitHub → Settings → Branches (or Rulesets) for `main`:

- Require a pull request before merging
- Require status checks to pass (CI workflow)
- Do not allow force pushes

If API/plan limits block automation, keep the same discipline manually.

## Related

- [CONTRIBUTING.md](../CONTRIBUTING.md) — contributor checks + personal-overlay push checklist  
- [AGENTS.md](../AGENTS.md) — architecture invariants + this workflow for agents  
- [AGENT_BUDGETS.md](AGENT_BUDGETS.md) — context/dump knobs, owners, calibrate scripts  
- [SECURITY.md](../SECURITY.md) — vulnerability reporting  
- [CONNECTORS.md](CONNECTORS.md) — fail-closed connectors contract  
