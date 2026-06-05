# Audit: repo goals vs current state (2026-06-02)

Context: explain commit `768afb4` diff vs `bf4fc04`, confirm nothing critical was “lost from git”, and checklist against the modular/agent/i18n/no-PII architecture.

---

## 1. Why `768afb4` shows −16 430 / +9 760 lines (not “deleted half the repo”)

| Fact | Detail |
|------|--------|
| Files deleted | **1**: `knowledge_bot/app/handlers/note_complete/pipeline.py` (logic folded into `complete.py`) |
| Files added | **4**: `complete.py`, `note_routing.py`, tests |
| Net line churn | Almost entirely **inside existing files**, especially YAML catalogs |

### Root cause: wrong duplicate of `messages.*.yaml.example` at `bf4fc04`

At **`bf4fc04`** both files were ~**4 615 lines** and **byte-identical at the top**:

- `config/messages.ru.yaml.example` — header even said `domain_messages.ru.yaml`
- `config/domain_messages.ru.yaml.example` — same content

So ~4.6k “domain” strings lived **twice** under `messages.ru` (misnamed duplicate), not under `domain_messages.ru`.

At **`768afb4`**:

| File | Lines @ bf4fc04 | Lines @ 768afb4 |
|------|-----------------|-----------------|
| `messages.ru.yaml.example` | 4615 | **598** (Telegram UI only) |
| `domain_messages.ru.yaml.example` | 4615 | **4727** (tools/agent/domain text) |

**~4 000 deletions in `messages.ru`** = removed duplicate domain catalog, not removed product code.

Similarly `messages.en.yaml.example`: **−4 488 / +757** (trim + reshape).

`domain_messages.en.yaml.example`: **−3 173 / +3 514** ≈ same size — **reorder/scrub**, not mass loss.

### REDACTED

No `REDACTED` in tracked `config/*.yaml.example` today. Historical PII scrub shows up as **large YAML replacements** (same keys, sanitized values), which inflates diff stats without deleting modules.

### Could we have “not pulled” files and lost server-only code?

**Unlikely for this diff:**

- Git only removed **one** Python module (pipeline → complete merge).
- Server prod files (`*.txt` prompts, `domain_messages.yaml`, `messages.yaml`, `.env`) are **gitignored by design** — they were never restored by `git pull`; deploy/rsync + local copies keep them.
- Risk is **local/server config drift**, not “Git deleted `finance_bot`”.

**What actually broke prod** (already addressed in `768afb4` + follow-ups):

- Loader preferred `.example` over author `domain_messages.yaml` → empty `pdmsg()`.
- Wrong `finance_bot/bot/agent_tools.py` (planning copy) in tree before fix.
- Missing `import time` in transactions core.

---

## 2. Goal checklist (your architecture)

| Goal | Status | Notes |
|------|--------|-------|
| **Merged host** | OK | `shared/telegram/host`, unified wire, domain adapters |
| **Modular bots** | OK | `CAP_MODULE_*`, capabilities profile, per-bot entrypoints |
| **Agent loop** | OK | `shared/agent/core.py`, tools registry, no scripted NLU-only host for finance queries |
| **No text in `.py`** | **In progress** | CI `test_no_cyrillic_in_py`; RU in YAML/`llm_context/*.example.txt` |
| **Prompts: `.example.txt` in git, `.txt` prod** | OK | `.gitignore` blocks `**/config/prompts/*.txt`; only `*.example.txt` tracked |
| **No PII in git** | OK | Examples sanitized; prod YAML/txt local |
| **i18n EN/RU** | OK | `AGENT_LOCALE`, `messages.{en,ru}.yaml`, `domain_messages.{en,ru}.yaml` |
| **Config over code** | **Partial** | Many paths/labels in YAML; see §3 |
| **Simple onboarding** | Partial | `shared/capabilities/onboarding_verify.py`, skills — document env + copy examples |

---

## 3. Hardcode / config gaps (priority)

### P1 — Agent transport defaults (your example)

`ModelRouter.chat_with_tools(..., temperature=0.2, tool_choice="auto", timeout=120)` and the same in `LLMClient` are **library fallbacks**.

**Today:** agent loop temperature comes from `config/agent/models.yaml` → `roles.analyze.temperature` (good).

**Still hardcoded in code:** `timeout`, `tool_choice` policy (`required` vs `auto` on iter 0), stream/chat temperatures in router signatures.

**Recommendation:** extend `config/agent/models.yaml.example`:

```yaml
roles:
  analyze:
    model: deepseek-chat
    temperature: 0.2
    timeout_sec: 120
  chat:
    temperature: 0.7
    timeout_sec: 90
```

Wire `shared/agent/core.py` + `ModelRouter` to read these (keep env override via existing patterns).

### P1 — `platform.yaml` / capabilities

Good pattern: `shared/agent/platform_config.py` (`agent.max_iters`, `knowledge_query.*`, etc.). Continue migrating magic numbers there instead of new caps in Python.

### P2 — Legacy menu routing

Fragments like `if agent_app.has_domain(DOMAIN_KNOWLEDGE) and is_knowledge_menu(text)` are **capability-driven**, not NLU scripts — acceptable, but could move button labels → `messages.*` only (mostly done).

### P2 — Kanban column names

Column titles live in `planning_bot/config/kanban_schema.yaml` (good). Code uses `BACKLOG_COLUMN`, `IN_WORK_COLUMN`, … from schema (good). Empty schema fallback columns were ASCII-only after CI fix — **require `kanban_schema.yaml` on prod** (copy from `.example`).

### P2 — `planning_bot/config/prompts/llm_context/`

New home for long RU/EN LLM context strings (CI-safe). **Prod:** copy `*.example.txt` → `*.txt` per prompt convention; localize RU in private `.txt` if examples stay EN.

### P3 — `scripts/fix_llm_cyrillic.py`

One-off maintainer script; optional move to `planning_bot/tools/` or delete after merge.

---

## 4. Prompts safety (do not break prod)

| Layer | Git | Prod |
|-------|-----|------|
| `config/agent/prompts/*.example.txt` | Yes | Copy → `*.txt` |
| `config/agent/prompts/*.txt` | **Ignored** | Author fills |
| `finance_bot/config/prompts/*.example.txt` | Yes | Same |
| `planning_bot/config/prompts/*.example.txt` | Yes | Same |
| `knowledge_bot/config/prompts/*.example.txt` | Yes | Same |

**Never commit** `*.txt` prod prompts or `domain_messages.yaml` / `messages.yaml` with personal data.

---

## 5. CI / current branch (post-`768afb4`)

| Check | Status |
|-------|--------|
| `tests/test_no_cyrillic_in_py.py` | Fixed locally (uncommitted): `dmsg`/`kmsg`/`lctx`, `llm_context` templates |
| `tests/test_action_log_format.py` | Updated for locale-aware log labels |

---

## 6. Recommended next iteration (after push)

1. Commit CI/i18n fixes + `llm_context` templates + this audit.
2. On server: `git pull`, rerun `./scripts/deploy.sh --prod --component unified --restart-unified` (or your usual targets).
3. Verify prod files exist: `config/domain_messages.yaml`, `config/messages.yaml`, `kanban_schema.yaml`, prompt `*.txt` (not only `.example`).
4. Implement P1: `models.yaml` `timeout_sec` + router wiring.
5. Optional: split EN/RU `llm_context` via `load_prompt` + `AGENT_LOCALE` if you want English examples in git but Russian prod without editing code.

---

## 7. Summary

The **−7k net lines** between `bf4fc04` and `768afb4` are **catalog hygiene** (duplicate `messages.ru` ≈ `domain_messages.ru` removed), plus normal refactors — **not** silent deletion of bot code from Git. Your modular/agent split is intact; main risks are **config loader order**, **prod YAML/prompt files off-git**, and **remaining numeric defaults in Python signatures** — not missing pulls from remote.
