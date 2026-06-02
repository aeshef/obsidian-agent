#!/usr/bin/env python3
"""
Пересобирает MOC-страницы (хабы) по config/hubs_registry.yaml.

  python tools/sync_hubs.py --vault /path
  python tools/sync_hubs.py --vault /path --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_bot.core.config import load_config


def _load_dotenv() -> None:
    import os

    for p in (
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        break


def _parse_front(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None
    return yaml.safe_load(m.group(1)) or {}


def _title(data: dict, p: Path) -> str:
    t = data.get("title")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return p.stem


def _tags_set(note_tags: list) -> set[str]:
    return {str(t).strip() for t in note_tags if t and str(t).strip()}


def _match_tags(flat: set[str], any_of: list[str], prefixes: list[str]) -> bool:
    for t in any_of:
        if t in flat:
            return True
    for pre in prefixes:
        p = pre.rstrip()
        for x in flat:
            if x == p or x.startswith(p + "/"):
                return True
    return False


def main() -> None:
    _load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path)
    ap.add_argument("--registry", type=Path, help="hubs_registry.yaml")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    vault: Path = args.vault or cfg.vault_path
    reg_path = args.registry or (cfg.agent_config_path / "hubs_registry.yaml")
    if not reg_path.exists():
        print("Нет registry — пропуск.", file=sys.stderr)
        return 0

    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    hubs = reg.get("hubs", [])
    if not isinstance(hubs, list) or not hubs:
        return 0

    from shared.vault_layout import knowledge_subdir

    kd = knowledge_subdir()
    db = vault / kd
    if not db.exists():
        return 0
    default_hub_dir = f"{kd}/_Хабы"

    for hub in hubs:
        if not isinstance(hub, dict) or not hub.get("id"):
            continue
        hid = str(hub["id"])
        title = hub.get("title", hid)
        fname = hub.get("filename", f"🗺️_Хаб_{hid}.md")
        dir_rel = Path(hub.get("directory", default_hub_dir))
        any_of = [str(x) for x in (hub.get("include_tags", []) or []) if x]
        pref = [str(x) for x in (hub.get("include_tag_prefixes", []) or []) if x]
        intro = (hub.get("intro") or "").strip()
        cap = int(hub.get("max_notes", 150))
        excl = [str(s) for s in (hub.get("exclude_paths_substr", []) or []) if s]

        if not (any_of or pref):
            print(
                f"  skip hub {hid!r}: no include_tags / include_tag_prefixes",
                file=sys.stderr,
            )
            continue

        matches: list[tuple[str, str, float]] = []
        for np in db.rglob("*.md"):
            if "Export" in str(np):
                continue
            slp = str(np).replace("\\", "/")
            if any(e in slp for e in excl):
                continue
            if np.name == fname:
                continue
            data = _parse_front(np)
            if not isinstance(data, dict):
                continue
            if data.get("type") == "hub" or data.get("hub_id"):
                continue
            tags0 = data.get("tags", [])
            if not isinstance(tags0, list) or not tags0:
                continue
            flat = _tags_set(tags0)
            if not _match_tags(flat, any_of, pref):
                continue
            rel = str(np.relative_to(vault).as_posix())
            matches.append((rel, _title(data, np), np.stat().st_mtime))
        matches.sort(key=lambda x: -x[2])
        matches = matches[:cap]
        wik = "\n".join(f"- [[{r}|{t}]]" for r, t, _ in matches) or "_(пусто)_"
        block_intro = f"{intro}\n\n" if intro else ""
        fm = {
            "type": "hub",
            "hub_id": hid,
            "date": date.today().isoformat(),
            "title": str(title),
            "tags": ["system/hub", f"meta/hub/{hid}"],
        }
        md = (
            "---\n"
            + yaml.dump(
                fm, allow_unicode=True, default_flow_style=False, sort_keys=False
            ).rstrip()
            + "\n---\n\n"
            + f"# {title}\n\n"
            + block_intro
            + "## Связанные заметки\n\n"
            + wik
            + "\n"
        )
        out = vault / dir_rel / fname
        if args.apply:
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists():
                o = out.read_text(encoding="utf-8", errors="ignore")
                if o.strip() == md.strip():
                    print(f"  ok (same): {out.relative_to(vault)}")
                    continue
            out.write_text(md, encoding="utf-8")
            print(f"  write: {out.relative_to(vault)} ({len(matches)} links)")
        else:
            print(
                f"--- dry-run {out} ({len(matches)} notes) ---\n" + md[:3000] + "\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
