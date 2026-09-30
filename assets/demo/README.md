# Product demo assets

## Obsidian vault walkthrough (~50 s)

Merged from four Screen Studio captures (goals → kanban → dashboards → graph).

| File | Size | Use |
|------|------|-----|
| `obsidian-demo.gif` | ~7.7 MB | GitHub / README preview (640×360, 7 fps) |
| `obsidian-demo.mp4` | ~7 MB | Hackathon form, Pet Projects, higher quality |
| `clips/` | — | Source GIFs (local only, gitignored) |
| `build/` | — | Full-res merge intermediate (local only) |

Order inside the merge: `clips/goals.gif` → `clips/tasks.gif` → `clips/dashboards.gif` → `clips/graph.gif` (PKM hub + local graph).

Rebuild after re-recording a clip:

```bash
cd assets/demo
# drop new files into clips/{goals,tasks,dashboards}.gif
ffmpeg -y -i clips/goals.gif -i clips/tasks.gif -i clips/dashboards.gif -i clips/graph.gif \
  -filter_complex "[0:v]fps=30,scale=1920:-2,setpts=PTS-STARTPTS[v0];[1:v]fps=30,scale=1920:-2,setpts=PTS-STARTPTS[v1];[2:v]fps=30,scale=1920:-2,setpts=PTS-STARTPTS[v2];[3:v]fps=30,scale=1920:-2,setpts=PTS-STARTPTS[v3];[v0][v1][v2][v3]concat=n=4:v=1:a=0[v]" \
  -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 18 build/obsidian-demo.mp4
ffmpeg -y -i build/obsidian-demo.mp4 -vf fps=24,scale=1280:-2 -c:v libx264 -crf 26 -movflags +faststart obsidian-demo.mp4
ffmpeg -y -i build/obsidian-demo.mp4 -vf "fps=7,scale=640:-2,split[s0][s1];[s0]palettegen=stats_mode=diff:max_colors=48[p];[s1][p]paletteuse" -loop 0 obsidian-demo.gif
```

Shoot script: [docs/_maintainer/DEMO_FILM_SHOOT.md](../../docs/_maintainer/DEMO_FILM_SHOOT.md).

## Telegram loop (~15 s)

| File | Role |
|------|------|
| `demo.gif` | README hero — Telegram → confirm → Obsidian note |
| `storyboard.png` / `.svg` | Fallback still |

See [docs/DEMO_CAPTURE.md](../../docs/DEMO_CAPTURE.md).

## Rules

- No real names, employers, balances, or identifying paths
- Prefer English UI (`AGENT_LOCALE=en`, `demo-vault-en`)
- Crop Telegram to the bot thread only
