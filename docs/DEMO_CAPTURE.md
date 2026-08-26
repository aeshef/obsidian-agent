# Capture a 15s product demo (no PII)

Record once; drop `demo.gif` or `demo.mp4` into `assets/demo/`.

## Script (≈15s)

1. **Telegram** — send `coffee 4.50` (or a photo of a receipt). Show confirm button.
2. **Obsidian** — open the new ledger note / kanban card / inbox note (English folders).
3. **Dashboard** — jump to finance or planning dashboard with a chart visible.

Optional B-roll: voice message → ASR text in chat.

## Hygiene

- `AGENT_LOCALE=en` for OSS screenshots
- Fake amounts only; blur any real balances
- Crop away phone number / @username if identifying
- Prefer Screen Studio / Kap / `ffmpeg` → GIF under ~5MB

## Embed

When the file exists, README can use:

```markdown
![demo](assets/demo/demo.gif)
```

Until then, the committed `storyboard.svg` stands in.
