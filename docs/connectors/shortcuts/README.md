# Phone / desktop Shortcut recipes

Apple does not allow shipping binary `.shortcut` files in a useful way for every
iOS version. This repo documents **recipes** you recreate in the Shortcuts app
(or Tasker on Android). Output must match the
[health snapshot format](../health/FORMAT.md).

## A. Health evening dump (iOS Shortcuts)

1. **Get** Health samples you care about (steps, weight, resting HR, …) for *Today*.
2. **Text** action — build lines:

   ```text
   ts: CURRENT_DATE (ISO 8601)
   source: iphone_shortcut
   steps: …
   weight_kg: …
   resting_hr_bpm: …
   ```

3. **Save File** into your Obsidian vault folder (iCloud Drive / Obsidian Sync path),
   name `YYYY-MM-DD, HH-MM.txt`.
4. Optional: **Send Email** to yourself with subject matching `GMAIL_IMAP_SUBJECT`
   if you use the Gmail health connector instead of direct file write.

Automation: run on a daily schedule (evening) or when you close the day.

## B. Calendar day dump (iOS)

1. **Find Calendar Events** for Today.
2. Format as plain text (title, start, end).
3. Append/Save to the calendar data path from `vault_paths` (see Obsidian setup docs).

Enable connector `apple_calendar` when ready.

## C. Mac context (macOS Shortcuts + optional LaunchAgent)

1. Shortcut gathers frontmost app / focus / battery (or your own fields).
2. Write `ts` + `source: mac` + fields into `Actions/Mac/YYYY-MM-DD, HH-MM.txt`.
3. Optional: install `scripts/install_mac_context_launchagent.sh` to run the
   Shortcut on an interval (`MAC_CONTEXT_SHORTCUT_NAME`).

**No Mac?** Skip this connector. The bot on a VPS does not need Mac context.

## D. Android (Tasker / Automate)

1. Read sensors / Health Connect values you already collect.
2. Write the same KV file into the vault folder synced by Obsidian Sync, Syncthing,
   or FolderSync.
3. Enable `health_snapshots: true` (alias of `apple_health`) in `capabilities.yaml`.

See [`samples/android_minimal.txt`](../health/samples/android_minimal.txt).

## Verify

```bash
./scripts/oa-python.sh -c "from planning_bot.services.iphone_health_fields import extract_raw_fields; print(extract_raw_fields(open('docs/connectors/health/samples/evening_checkin.txt').read()))"
```

Or drop a sample into the vault health folder and ask Telegram for a health summary.
