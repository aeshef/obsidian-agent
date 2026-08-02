"""Agent core types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class ModelRole(str, Enum):
    PARSE = "parse"
    ANALYZE = "analyze"
    CHAT = "chat"


class Domain(str, Enum):
    FINANCE = "finance"
    PLANNING = "planning"
    KNOWLEDGE = "knowledge"
    GENERAL = "general"


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    category: str = "general"
    always: bool = False
    serial: bool = False


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    id: str
    name: str
    content: str


@dataclass
class AgentMessage:
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    ts: str | None = None


@dataclass
class AgentContext:
    user_id: int
    domain: str
    question: str
    system_prompt: str
    history: list[AgentMessage] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentAnswer:
    text: str
    media_files: list[tuple[str, str]] = field(default_factory=list)


KB_MEDIA_EXTRAS_KEY = "kb_media_files"
# Dashboard chart PNGs queued by send_vault_charts — kept separate from KB note media.
CHART_MEDIA_EXTRAS_KEY = "chart_media_files"


@dataclass
class RouteDecision:
    domain: Domain
    intent: str
    confidence: float
    via: str  # rule | llm
