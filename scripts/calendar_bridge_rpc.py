"""Restricted JSON-over-SSH protocol for the trusted Mac calendar worker."""
import json
import sys
from planning_bot.services.calendar_bridge import rpc

if __name__ == "__main__":
    try:
        print(json.dumps(rpc(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}))
        sys.exit(1)
