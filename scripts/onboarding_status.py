#!/usr/bin/env python3
"""Print onboarding status (what is ready / missing / next asks)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.capabilities.onboarding_status import collect_status, format_status_text  # noqa: E402
from shared.capabilities.profile import clear_capabilities_cache  # noqa: E402
from shared.setup.load_env import load_repo_env  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true", help="Machine-readable JSON")
    p.add_argument("--locale", default=None)
    args = p.parse_args()

    load_repo_env(_ROOT)
    clear_capabilities_cache()
    data = collect_status(locale=args.locale)

    if args.json:
        # dataclasses in items
        payload = dict(data)
        payload["items"] = [
            {"id": i.id, "ok": i.ok, "detail": i.detail, "required": i.required}
            for i in data["items"]
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_status_text(data), end="")

    # exit 1 if blocking errors when capabilities exist
    if data["capabilities_present"] and data["errors"]:
        return 1
    if not data["capabilities_present"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
