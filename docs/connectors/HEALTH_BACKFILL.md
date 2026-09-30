# iPhone daily revisions (v2)

This is a format and manual Shortcuts recipe, not an installed iOS automation.
The original daily Shortcut remains compatible. A test copy must be built and
verified on iPhone; Health actions must not be executed on Mac.

## One packet = one day + one metric group

```text
---
ts: 2026-09-01T00:00:00+03:00
schema_version: 2
source: iphone_backfill_v2
measurement_day: 2026-09-01
captured_at: 2026-09-13T20:00:00+03:00
metric_group: nutrition
read_status: ok
calories_kcal: 2100
proteins_g: 120
fats_g: 70
carbs_g: 240
empty_fields: water_ml,weight_kg
---
```

Values above are synthetic format examples, not user measurements.

`ts` identifies the measurement day; `captured_at` is an actual date/time with UTC
offset when that group was read. Never format it as an ambiguous localized string.
Group fields and lookbacks are in `health_backfill.yaml.example`. A failed Health
action must stop that group before saving an `ok` packet. `empty_fields` means
the latest export has no available value, not a measured zero. Empty reads cannot
prove that Health read permission was granted; check a known populated date on
device. An omitted field is not a deletion.

The receiver merges revisions independently for each day/group, using actual
capture time rather than message arrival order or field count. Exported values
and explicit empty fields are replaced, unrelated groups stay intact. The daily
query/weekly summary and charts consume revisions. Conflicting same-time group
revisions should not be produced; preserve packet content when retrying.

## Suggested schedule

- Morning/evening: today and yesterday, all selected groups.
- Daily: nutrition for 14 calendar days; activity/vitals/sleep for 7.
- Weekly reconciliation: 90 days, persisted queue, processed in small chunks.
- After opening/closing the food diary: nutrition refresh, throttled; not proof
  that the food app has already committed its edits to Health.
- Missing collection jobs and unsent packets survive the current execution.

Use separate Shortcuts for one day/group, collecting a bounded queue of jobs, and
delivering saved packets. Process three days per invocation as a starting limit;
reduce it on timeout. A 90-day scan takes multiple invocations, not a single long
background loop. Prioritize missing jobs and keep weekly jobs progressing.

Every Health Find action must reference `DayStart` and `NextDayStart` (actual Date
variables), not Today/Yesterday/current date. Use a half-open daily interval where
possible. For inclusive UI `between`, exclude records at NextDayStart to avoid
double counting. Sum nutrition from the chosen authoritative app, use the last
weight measurement inside the day, and never sum duplicate overlapping sources.
Sleep needs overlap selection and a declared attribution rule, not just start
date: select intervals ending that day for wake-day attribution; merge overlaps
and exclude In Bed/Awake from asleep duration.

## Durable file queue and email limitations

Write each packet first to an Outbox folder with a unique stable filename. Only
then send that saved content. A retry must preserve the packet and captured_at.
Do not concatenate several daily KV packets into one message: the legacy text
parser reads one packet per message/file.

A successful Send Email action confirms handoff to Mail, not ingestion by
Obsidian or the server. Keep an Archive copy for at least the reconciliation
window. If delivery is uncertain, resend the same packet; v2 filenames are
content-derived so retries do not create extra daily revisions. A complete
automatic acknowledgement-to-iPhone channel is not implemented here. Do not
delete the only packet copy based solely on the email action returning.

The sender validates `schema_version: 2` before Mail handoff. Empty or malformed
files go to `Rejected` and cannot block later packets. Moving a valid packet to
`SentArchive` uses replace-existing semantics because equal content has an equal
SHA-256 filename. The synchronization shortcut collects before it sends, so a
Mail failure never prevents the current Health read from reaching Outbox.

## Test before enabling automations

1. Use an isolated test folder and subject, outside the production subject filter.
2. Export one past day; compare kcal/macros with the source app and Health.
3. Add/correct a real entry for that past day, export again, verify captured_at
   changes while measurement_day does not. The later result replaces the earlier.
4. Retry the exact packet; its daily values and sample weight must not double.
5. Leave a group unavailable; it must not erase unrelated groups or become zero.
6. Interrupt a three-day job halfway; saved packets survive, unfinished jobs remain.
7. Turn off network after saving, then restore it; retry delivery from Outbox.
8. Check sleep across midnight, day boundaries, and timezone changes.
9. Test a locked-phone trigger; verify a missed run is recovered by a later run.
10. After passing these checks, enable schedules and switch the production
    receiver only after deploying the v2 parser and chart changes.

## Gmail without inbox clutter

Create an ASCII label `ObsidianMetrics`. Create a filter using the exact sender
and distinctive existing production subject. Apply the label; initially leave
messages in Inbox. Configure **every active receiver** with
`GMAIL_IMAP_MAILBOX=ObsidianMetrics`, run it and verify one real packet arrives.
Then enable Skip Inbox (Archive), optionally Mark as read, and apply the filter to
existing matching messages. Do not choose Delete. If Gmail shows Show in IMAP for
the label, enable it. Missing labels produce an explicit receiver error; there is
no fallback to Inbox. Selection is read-only and message bodies use BODY.PEEK[].

Archiving moves messages out of Inbox, not out of Gmail. A label is an intake
folder, not a transactional queue with a server acknowledgement.

The receiver scans unprocessed messages over a 180-day recovery window and
applies the exact subject filter on the IMAP server. The regular Mac sync does
not limit intake to today/yesterday, so sleep or a prolonged shutdown does not
discard older queued revisions. Processed Message-IDs make repeat scans
idempotent.

Apple: https://support.apple.com/en-ie/guide/shortcuts/apdc11deb2c1/ios
Google: https://support.google.com/mail/answer/9259770
