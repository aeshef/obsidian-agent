"""Single-bot host: orchestrates domain bots behind one Telegram process."""
from shared.telegram.host.bootstrap import run_host_bot

__all__ = ["run_host_bot"]
