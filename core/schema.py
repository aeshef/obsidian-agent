from __future__ import annotations

import re
from pathlib import Path
from typing import List, Set

from knowledge_bot.core.config import load_config
from knowledge_bot.core.settings import load_types_config


VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}")


DEFAULT_FIELDS = {"type", "title", "created", "tags", "attachments", "source", "form", "raw_dir"}


def allowed_fields_for_type(type_name: str) -> List[str]:
    cfg = load_config()
    types_cfg = load_types_config(cfg.agent_config_path)
    template_name = types_cfg.template_for(type_name)
    template_path = cfg.templates_path / template_name
    if not template_path.exists():
        return []
    text = template_path.read_text(encoding="utf-8", errors="ignore")
    fields: Set[str] = set()
    for m in VAR_RE.finditer(text):
        var = m.group(1)
        # skip nested like attachments.links etc. We only allow top-level known fields plus simple ones
        if "." in var:
            var = var.split(".", 1)[0]
        if var in DEFAULT_FIELDS:
            continue
        fields.add(var)
    return sorted(fields)


