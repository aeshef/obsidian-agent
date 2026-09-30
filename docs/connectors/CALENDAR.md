# Apple Calendar: authority, freshness, and writes

Apple Calendar owns events. The assistant reads a local/native replica; it never
treats an export timestamp as the time of an event or an empty stale list as free time.

## Contract

- Mac worker polls the server write queue every 60 seconds.
- Every 300 seconds it exports a complete EventKit snapshot, 90 days back and
  90 days ahead (through the end of the last day, exclusive upper bound).
- Recurring occurrences, stable native/calendar identifiers, all-day events,
  time zones, moves, and deletions are represented by the native snapshot.
- Each complete snapshot replaces its entire declared coverage, including empty
  days. Failed/partial exports never overwrite the last good snapshot.
- Events older than the moving window become monthly archive totals. They are
  not counted again on the next import. Outside known coverage, availability is unknown.
- A successful unchanged export still advances source freshness. Data older than
  15 minutes are labelled stale. Calendar snapshot metadata reaches the VPS directly
  over the existing SSH connection, independently of charts and bulk vault sync.
- Charts render from the replica on the next normal sync; they do not gate ingestion.
- Mac sleep/offline pauses native export and writes. Requests stay queued and are
  not reported as created. The bridge resumes on the next launchd run after wake.
- The old Shortcuts TXT remains a compatibility input until the first native
  snapshot. Once native authority is established, it cannot overwrite the replica.

## Agent tools

`list_calendar_calendars` lists calendars, IDs, and write permissions.
`create_calendar_event` accepts title, offset-aware ISO start/end, optional calendar
name/ID, notes, and location. Default calendar comes from personal bridge config.
It is offered only when planning, Apple Calendar, and bridge writes are enabled.
Use only for an explicit user request. Resolve ambiguous time/duration before calling.
It does not invite attendees, create recurrence rules, or edit/delete existing events.

`get_calendar_event_status` reads the caller's request. Only `created` plus a native
event ID confirms creation. `queued`/`processing` mean pending. `outcome_unknown`
must not be replayed as a new event: reconcile the existing request/event first.

The queue uses a hash of normalized event payload and actor for retry idempotency,
SQLite transactions, lease tokens, and native event URL markers. After an uncertain
attempt, a worker may only find the existing event, never blindly create it again.
Native writes are read back before acknowledging. No external HTTP listener is opened.

## Installation

Build `scripts/calendar_eventkit.swift` into a signed macOS app bundle named
`Obsidian Calendar Bridge.app`, with Calendar full-access usage description.
Grant it full Calendar access. Configure `config/agent/calendar_bridge.yaml`
from its example on both the Mac and server; default examples are disabled.
The Mac requires the existing SERVER / SERVER_BOTS / VAULT_PATH environment.
Schedule `scripts/run_calendar_bridge.sh` via launchd at `poll_seconds`.
The native helper defaults to `~/Applications/Obsidian Calendar Bridge.app/Contents/MacOS/calendar-eventkit`.

State: server `calendar_bridge.db`; Mac `.sync/calendar_bridge_status.json`;
source metadata in the configured calendar JSON. `scripts/check_pipeline_freshness.py`
checks iPhone capture age and calendar capture age independently of sync success.
