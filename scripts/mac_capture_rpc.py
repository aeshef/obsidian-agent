"""Internal authenticated SSH receiver, not a bot-facing execution endpoint."""
import json
import sys
from planning_bot.services.mac_capture import receive

if __name__ == "__main__":
    try:
        print(json.dumps(receive(json.load(sys.stdin)["events"])))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}))
        sys.exit(1)
