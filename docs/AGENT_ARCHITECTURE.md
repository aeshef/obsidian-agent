# Durable assistant architecture

The existing agent loop is retained. `shared/agent_runtime` adds SQLite tables to
`AGENT_MEMORY_DB`; `config/agent/architecture.yaml.example` controls limits and can
be overridden with `architecture.yaml`. Set `enabled: false` to disable runtime
tools, archival, context injection and the follow-up worker without deleting data.

## Memory and context

Short session history remains bounded. New dialogue is also archived in FTS5 with
180-day/10,000-row per-owner retention. Historical messages already deleted by the
old session pruner cannot be reconstructed. Search is lexical, not semantic.
Facts, decisions and preferences carry their original message/tool evidence,
certainty, validity range, project ID and replacement links. Superseded versions
are excluded from active context. Existing confirmed insights retain their store;
confirmation now preserves evidence, repeated confirmation is rejected, and
owner-scoped revision preserves the old version. Legacy records with no evidence
remain explicitly unattributed. Procedures are proposals until user approval;
they cannot edit system prompts or expand permissions. Dialogue/record deletion is
available on explicit request.

Project cards contain a summary and links, not duplicate source documents. Context
selection uses query overlap plus a one-hour recent-project fallback. It includes
bounded relevant active records and open assignments. This is a deliberately
small deterministic baseline; it does not claim semantic entity resolution.
Retrieved content is data, not instructions. Large tool results remain available
through an indexed paging tool instead of silent truncation.

## Mutation receipts

Tools opt in via `mutating=True` and a read-back verifier. Kanban and calendar
writes use this contract; financial imports retain their existing transactional
idempotency and undo workflow. A Telegram message supplies the stable request
key. The journal atomically reserves (owner, request, tool, arguments hash).
An exception or interrupted operation remains unknown and cannot be replayed
within that request. A different user message is a new request; callers must
inspect an unknown receipt before deliberately retrying it.

Receipts distinguish verified, pending, unverified, rejected and outcome_unknown.
Calendar queued is pending, not created. Kanban verification reloads the board.
Uncertain writes override a success-looking final answer with an explicit unknown
result. Answer streaming is suppressed after a mutation receipt so the final guard runs before delivery.

## Follow-ups

A future check must be explicitly requested and persisted before it is promised.
The host owns one worker task. Only registered `read_only=True` tools in the
configured allowlist may execute. Module removal or read permission revocation
blocks subsequent checks. Conditions: a nonempty result, substring, JSON subset,
or change from the first successful baseline. Every job has a due time, expiry,
checkpoint, lease, failure counter and owner. Cancellation wins over an in-flight
check. Failed probes back off at the configured polling interval and terminate at
the failure limit. Completed jobs do not restart. No background LLM loop or future
arbitrary writes are supported.

Notifications use an at-most-once attempt. A delivery failure is marked unknown
and visible in the job list; uncertain delivery is not retried and may require
manual inspection. A crash during sending may leave `sending`; this also means
unknown delivery, not success. No exactly-once Telegram guarantee is claimed.

## Regression suite

`tests/test_agent_architecture.py` checks user isolation, source retention,
revision, expiry, procedure review, duplicate writes, unknown outcomes, durable
checks, tool revocation and concurrent cancellation. Existing finance, calendar,
health and kanban tests remain the domain acceptance suite. No test writes real
transactions or sends Telegram messages. Test fixtures contain synthetic data.
