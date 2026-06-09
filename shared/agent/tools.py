"""Tool registry and dynamic selection by query."""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, get_args, get_origin, get_type_hints

from shared.agent.types import Tool

log = logging.getLogger("shared.agent.tools")

_JSON_TYPE_MAP = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema_for_annotation(ann: Any) -> dict[str, Any]:
    if ann is inspect.Parameter.empty:
        return {"type": "string"}
    origin = get_origin(ann)
    if origin is type(None):
        return {"type": "string"}
    if origin is list:
        return {"type": "array", "items": _schema_for_annotation(get_args(ann)[0] if get_args(ann) else str)}
    if origin is dict:
        return {"type": "object"}
    args = get_args(ann)
    if origin is not None and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _schema_for_annotation(non_none[0])
    if ann in _JSON_TYPE_MAP:
        return {"type": _JSON_TYPE_MAP[ann]}
    return {"type": "string"}


def _build_parameters_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    hints = get_type_hints(fn, include_extras=True)
    sig = inspect.signature(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("ctx", "context"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        ann = hints.get(name, str)
        props[name] = _schema_for_annotation(ann)
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def tool(
    *,
    category: str = "general",
    always: bool = False,
    serial: bool = False,
    name: str | None = None,
):
    """Register async function as Tool when adding to ToolRegistry."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn._agent_tool_meta = {  # type: ignore[attr-defined]
            "category": category,
            "always": always,
            "serial": serial,
            "name": name or fn.__name__,
            "description": (fn.__doc__ or fn.__name__).strip().split("\n")[0],
            "parameters": _build_parameters_schema(fn),
        }
        return fn

    return decorator


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, fn: Callable[..., Any]) -> None:
        meta = getattr(fn, "_agent_tool_meta", None)
        if not meta:
            raise ValueError(f"{fn.__name__} is not decorated with @tool")
        t = Tool(
            name=meta["name"],
            description=meta["description"],
            parameters=meta["parameters"],
            handler=fn,
            category=meta["category"],
            always=meta["always"],
            serial=bool(meta.get("serial")),
        )
        self._tools[t.name] = t

    def register_many(self, fns: list[Callable[..., Any]]) -> None:
        for fn in fns:
            self.register(fn)

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        selected = names or self.names()
        out: list[dict[str, Any]] = []
        for n in selected:
            t = self._tools[n]
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
            )
        return out


async def select_tools(
    query: str,
    registry: ToolRegistry,
    *,
    domain: str = "general",
) -> list[str]:
    """LLM selects tool subset; @tool(always=True) added automatically."""
    from shared.agent.llm_classify import select_tools_llm

    return await select_tools_llm(query, registry, domain=domain)
