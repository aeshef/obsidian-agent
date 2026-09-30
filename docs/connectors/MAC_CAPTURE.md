# Native Mac capture

The native collector captures foreground application names/identifiers, application
changes, idle duration, sleep/wake and session activation. It does not read window
contents, screenshots, keys, browser history or clipboard. Existing Shortcut
collection can remain as optional enrichment; native duration analytics uses only
native events and does not double-count legacy snapshots.

Configuration: `config/agent/mac_capture.yaml.example`; personal overlay
`mac_capture.yaml`. Both `enabled` and the `mac_context` capability must be on.
`upload_enabled` is a separate opt-in. With upload disabled, the queue and preview
stay under Application Support, outside the synced vault. Nothing from this
collector is sent by SSH or the existing vault synchronization in this mode.

## Operation

- `scripts/mac_capture.swift` emits atomic, uniquely identified event files and a
  heartbeat every 60 seconds. launchd restarts it on abnormal termination.
- `scripts/mac_capture_worker.py` runs every 60 seconds. It commits events to
  SQLite with synchronous FULL before removing spool files. Malformed files stay
  in the spool and make status degraded.
- Delivery retries the same IDs over the existing authenticated SSH connection;
  `scripts/mac_capture_rpc.py` acknowledges only after the server has committed
  events and updated derived data. Lost acknowledgements cause harmless retries.
- Local-only mode never acknowledges remote delivery. Pending data is retained.
- A heartbeat older than 180 seconds prompts a collector restart. Startup gets a
  grace period; a launchctl timeout is reported as unknown, not claimed successful.
- Local state: `~/Library/Application Support/obsidian-agent/mac-capture/`.
  `status.json` reports source freshness, pending events, errors and delivery mode.
  With upload enabled it also publishes `.sync/mac_capture_status.json` in the vault.

## Analytics and retention

Native snapshots are materialized into a bridge-owned daily file
`YYYY-MM-DD, 00-00_9001.txt`, containing regular heartbeat samples. Existing
Shortcut files are preserved. Raw transition events remain in SQLite.

Intervals longer than 90 seconds or crossing collector session IDs are unknown,
not continued foreground activity. A recorded sleep state within the same
collector session remains sleep until its next event. Active/idle accounting is
an estimate from observations; foreground application time is not proof of work.

The bot tool `get_mac_capture_summary` reports active/idle/sleep/unknown seconds,
application durations, source age and uncovered time. Dates use the configured
timezone; stored aggregates are UTC hours (whole-hour timezone offsets supported
for exact day boundaries).

Acknowledged raw events: 90 days plus a boundary-day buffer. Hourly aggregates:
730 days. Pending events are never removed by TTL. Pruning affects only this
collector's records and bridge-owned daily files, not old Shortcut logs.
Missing historical activity that was never captured cannot be reconstructed.

## Validation

Run the Mac capture tests for replay, lost/invalid acknowledgements, corrupt spool
retention, crashes/session boundaries, long gaps, and the existing snapshot parser.
For an installed collector: compare launchd PID and session ID before/after
terminating only the collector process; verify new samples arrive, old queued IDs
remain and status returns fresh. For delivery, lose the response after server
commit and verify retry acknowledges the same IDs without additional records.
