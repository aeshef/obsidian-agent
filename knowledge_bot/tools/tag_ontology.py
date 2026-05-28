#!/usr/bin/env python3
"""
Онтология тегов: LLM предлагает слияния → data/tag_ontology_proposal.yaml;
  правки вносятся в config/tag_ontology.yaml, затем:

  python tools/tag_ontology.py apply
  python tools/tag_ontology.py apply --apply
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.settings import load_prompt
from knowledge_bot.services.tag_remap import apply_tag_mappings, extract_mapping_from_ontology_file
from knowledge_bot.services.tags_inventory import scan_all_notes


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


def _tags_by_namespace(
    inv: dict[str, Any], namespaces: list[str]
) -> dict[str, list[tuple[str, int, list[str]]]]:
    out: dict[str, list[tuple[str, int, list[str]]]] = defaultdict(list)
    tags = inv.get("tags", {}) or {}
    for full, info in tags.items():
        if "/" not in str(full):
            continue
        ns, _ = str(full).split("/", 1)
        if ns not in namespaces:
            continue
        cnt = int(info.get("count", 0) or 0)
        ex = list(info.get("examples", []) or [])[:2]
        out[ns].append((str(full), cnt, ex))
    for n in out:
        out[n].sort(key=lambda x: (x[1], x[0]))
    return dict(out)


def run_propose(cfg) -> int:
    inv = scan_all_notes(cfg.vault_path)
    pcfg_path = cfg.agent_config_path / "tag_ontology.yaml"
    if not pcfg_path.exists():
        ex = cfg.agent_config_path / "tag_ontology.yaml.example"
        if ex.exists():
            pcfg_path = ex
    pcfg: dict = {}
    if pcfg_path.exists():
        pcfg = yaml.safe_load(pcfg_path.read_text(encoding="utf-8")) or {}
    pconf = pcfg.get("propose", {}) or {}
    namespaces = list(
        pconf.get("namespaces", ["topic", "domain"])
    )
    max_batch = int(pconf.get("max_per_llm_batch", 50))
    model = pconf.get("model", "deepseek-chat")
    (cfg.agent_config_path / "data").mkdir(exist_ok=True)
    out_p = cfg.agent_config_path / "data" / "tag_ontology_proposal.yaml"

    by_ns = _tags_by_namespace(inv, namespaces)
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    system = load_prompt(cfg.agent_config_path, "tag_ontology_propose")
    all_maps: dict[str, str] = {}
    for ns, rows in by_ns.items():
        for i in range(0, len(rows), max_batch):
            batch = rows[i : i + max_batch]
            user_obj = {
                "namespace": ns,
                "tags": [
                    {"tag": t, "count": c, "examples": ex} for t, c, ex in batch
                ],
            }
            res = llm.chat_json(
                system, json.dumps(user_obj, ensure_ascii=False), model=str(model), timeout=180.0
            )
            mp = (res.content or {}) if res else {}
            m = mp.get("mappings") or mp
            if isinstance(m, dict):
                for a, b in m.items():
                    a, b = str(a).strip(), str(b).strip()
                    if a and b and a != b and a.startswith(
                        f"{ns}/"
                    ) and b.startswith(f"{ns}/"):
                        all_maps[a] = b
    out_doc: dict = {
        "propose_only": True,
        "namespaces": namespaces,
        "mappings": all_maps,
        "hint": "Скопируй проверенные пары в config/tag_ontology.yaml under mappings, затем: tag_ontology.py apply --apply",
    }
    out_p.write_text(
        yaml.dump(out_doc, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"OK: {out_p} ({len(all_maps)} маппингов)")
    return 0


def run_apply(cfg, do_write: bool) -> int:
    ont = cfg.agent_config_path / "tag_ontology.yaml"
    if not ont.exists():
        ex = cfg.agent_config_path / "tag_ontology.yaml.example"
        ont = ex if ex.exists() else ont
    m = extract_mapping_from_ontology_file(ont)
    if not m:
        print("Нет mappings в config/tag_ontology.yaml", file=sys.stderr)
        return 1
    st = apply_tag_mappings(
        cfg.vault_path, m, dry_run=not do_write
    )
    print(st)
    return 0 if st.get("ok") else 1


def main() -> int:
    _load_dotenv()
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(
            "tag_ontology.py propose  — LLM, пишет data/tag_ontology_proposal.yaml\n"
            "tag_ontology.py apply [--apply]  — сухой прогон / запись (из config/tag_ontology.yaml)\n"
            "  --vault /path/optional",
        )
        return 0
    if "--vault" in argv:
        i = argv.index("--vault")
        if i + 1 < len(argv):
            import os
            os.environ["VAULT_PATH"] = argv[i + 1]
    cfg = load_config()
    if argv[0] == "propose":
        return run_propose(cfg)
    if argv[0] == "apply":
        return run_apply(cfg, do_write=("--apply" in argv))
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
