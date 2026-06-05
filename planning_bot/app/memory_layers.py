"""Planning-specific agent memory layer (recent action log chain)."""
from __future__ import annotations
from shared.agent.types import AgentContext, AgentMessage

class PlanningActionLogLayer:
    """Inject recent kanban/action events into the agent context."""

    async def read(self, ctx: AgentContext) -> str:
        bot = ctx.extras.get('bot')
        if bot is None or bot.logger is None:
            return ''
        try:
            text = bot.logger.get_recent_events_chain()
            return (text or '').strip()
        except Exception:
            return ''

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        return