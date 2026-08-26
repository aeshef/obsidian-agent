"""Shared libraries for obsidian-agent bots."""

def __getattr__(name: str):
    if name == "run_host_bot":
        from unified_bot.host.bootstrap import run_host_bot
        return run_host_bot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["run_host_bot"]
