# Phone / desktop Shortcut recipes

Apple does not allow shipping binary `.shortcut` files in a useful way for every
iOS version. This repo documents **recipes** you recreate in the Shortcuts app
(or Tasker on Android). Health output must match the
[health snapshot format](../health/FORMAT.md).

## Optional starter Shortcuts (iCloud)

Public templates you can **Get Shortcut** → duplicate → rename paths/labels for
your vault. UI strings in these templates may be **Russian**; treat them as
structure references (actions + file targets), not as the final English copy.

| Connector | Role | iCloud link |
|-----------|------|-------------|
| `mac_context` | Desktop context snapshots (frontmost app / focus / …) | [Mac Context](https://www.icloud.com/shortcuts/034abdffeb82457395ea6a482a841133) |
| `apple_health` / `health_snapshots` | iPhone health / day context → vault KV files | [iPhone context](https://www.icloud.com/shortcuts/0baed2509a444f4d91d6047f6750fbe2) |
| `apple_calendar` | Day calendar dump → vault calendar path | [Calendar (Obsidian)](https://www.icloud.com/shortcuts/b8f0b1fc20d34903897c4bf95fa89be0) |

After install: point Save File / Append paths at your `VAULT_PATH` folders from
`vault_paths` (EN or RU locale), enable the matching connector in
`capabilities.yaml`, and set `MAC_CONTEXT_SHORTCUT_NAME` if you use the Mac
LaunchAgent.

If an iCloud link 404s, the share was unpublished — rebuild from the recipes
below or ask the maintainer to re-publish.

## A. Health evening dump (iOS Shortcuts)

Starter: [iPhone context](https://www.icloud.com/shortcuts/0baed2509a444f4d91d6047f6750fbe2) (or build manually):

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

Starter: [Calendar (Obsidian)](https://www.icloud.com/shortcuts/b8f0b1fc20d34903897c4bf95fa89be0) (or build manually):

1. **Find Calendar Events** for Today.
2. Format as plain text (title, start, end).
3. Append/Save to the calendar data path from `vault_paths` (see Obsidian setup docs).

Enable connector `apple_calendar` when ready.

## C. Mac context (macOS Shortcuts + optional LaunchAgent)

Starter: [Mac Context](https://www.icloud.com/shortcuts/034abdffeb82457395ea6a482a841133) (or build manually):

1. Shortcut gathers frontmost app / focus / battery (or your own fields).
2. Write `ts` + `source: mac` + fields into `Actions/Mac/YYYY-MM-DD, HH-MM.txt`
   (or the EN/RU path from `vault_paths`).
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
