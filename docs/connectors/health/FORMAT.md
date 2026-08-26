# Health snapshots — portable format

Health tools do **not** talk to Apple Health, Google Fit, or Health Connect APIs.
They read **plain-text key/value files** in the vault (default folder from
`vault_paths`: often `IPhone/` or `Actions/Health/`).

Any phone or desktop can produce the same files:

| Producer | How |
|----------|-----|
| iPhone Shortcuts | Write File / Append to vault (or email → Gmail IMAP sync) |
| Android Tasker / Automate / MacroDroid | Write the same KV text to Obsidian Sync / Syncthing folder |
| Manual | Paste into a `.txt` in the vault |
| Wearable export script | Cron / systemd drops a daily file |

## File location

Enable connector `apple_health` **or** YAML alias `health_snapshots: true`
(same flag). Drop files where your vault layout expects health snapshots
(see `config/vault_paths.*.yaml.example`).

Suggested filename: `YYYY-MM-DD, HH-MM.txt` (sortable).

## Required shape

```text
ts: 2026-08-26T21:30:00
source: android_tasker
steps: 8432
weight_kg: 72.4
resting_hr_bpm: 58
hrv_ms: 45
active_calories_kcal: 420
water_ml: 1500
note: evening check-in
```

Rules:

- One `key: value` per line (ASCII keys preferred).
- `ts` — ISO-8601 or `DD.MM.YYYY, HH:MM` (see `health_parse.yaml` formats).
- `source` — free string (`iphone_shortcut`, `android_tasker`, `manual`, …).
- Numeric metrics use the **canonical** names below (or aliases from
  `config/agent/health_parse.yaml`).
- Blocks may be separated by a line containing only `---`.

## Canonical metric keys

At least one of these should be present for a file to count as a health snapshot:

`steps`, `resting_hr_bpm`, `weight_kg`, `hrv_ms`, `calories_kcal`,
`active_calories_kcal`, `heartbeat_load`

Common extras: `water_ml`, `bmi`, `fat_pct`, `proteins_g`, `fats_g`, `carbs_g`,
`sleep_interval`, `blood_oxygen_pct`, `body_temp_c`, `exercise_min`, …

Copy aliases from [`config/agent/health_parse.yaml.example`](../../config/agent/health_parse.yaml.example)
into gitignored `health_parse.yaml` if your exporter uses different names
(RU Shortcuts keys, Samsung Health labels, etc.).

## Samples in this repo

| File | Role |
|------|------|
| [`samples/evening_checkin.txt`](samples/evening_checkin.txt) | Typical evening metrics |
| [`samples/android_minimal.txt`](samples/android_minimal.txt) | Minimal Android / Tasker dump |

Copy a sample into your vault health folder and ask the bot for today’s health
summary to verify parsing.

## Related

- Shortcut recipes (iOS): [`../shortcuts/README.md`](../shortcuts/README.md)
- Hosting without Mac: [`../HOSTING_WITHOUT_MAC.md`](../HOSTING_WITHOUT_MAC.md)
