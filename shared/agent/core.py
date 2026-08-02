"""Agent loop: tool selection → LLM → execute tools → repeat."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from shared.agent.router import ModelRouter
from shared.agent.tools import ToolRegistry, select_tools
from shared.agent.progress import AgentProgress, NullAgentProgress, answer_stream_enabled
from shared.agent.types import AgentContext, AgentMessage, ModelRole, ToolCall, ToolResult
from shared.llm import LLMResponse

log = logging.getLogger("shared.agent.core")

def _max_iters() -> int:
    from shared.agent.platform_config import platform_int

    try:
        env = os.environ.get("AGENT_MAX_ITERS")
        if env is not None and str(env).strip():
            return max(1, int(env))
    except ValueError:
        pass
    return max(1, platform_int("agent", "max_iters", default=6))


def agent_messages_to_api(messages: list[AgentMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        content = m.content or ""
        if m.ts and m.role in ("user", "assistant"):
            content = f"[at {m.ts}] {content}"
        if m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        elif m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or ""})
        else:
            out.append({"role": m.role, "content": content})
    return out


_CURRENCY_IN_TEXT = re.compile(
    r"(?:\d[\d\s]*(?:[.,]\d+)?)\s*(?:₽|rub\.?|RUB)",
    re.IGNORECASE,
)


def _warn_ungrounded_currency(answer: str, tool_bodies: list[str]) -> None:
    """Log when answer contains amounts not present in tool outputs (does not block answer)."""
    if not answer or not _CURRENCY_IN_TEXT.search(answer):
        return
    blob = "\n".join(tool_bodies)
    for m in _CURRENCY_IN_TEXT.finditer(answer):
        frag = m.group(0).replace(" ", "")[:24]
        if frag and frag not in blob.replace(" ", ""):
            log.warning(
                "agent answer may contain ungrounded amount %r (not in tool outputs)",
                m.group(0).strip(),
            )
            return


def parse_tool_calls(raw: list[dict[str, Any]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in raw or []:
        fn = item.get("function") or {}
        name = fn.get("name") or ""
        args_raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(id=str(item.get("id", "")), name=name, arguments=args))
    return calls


async def execute_tool(
    tc: ToolCall,
    registry: ToolRegistry,
    ctx: AgentContext,
    *,
    allowed_names: set[str] | None = None,
) -> ToolResult:
    if allowed_names is not None and tc.name not in allowed_names:
        from shared.agent.platform_config import platform_int
        from shared.i18n import msgf

        hint_max = platform_int("agent", "tool_denied_hint_max", default=12)
        allowed = sorted(allowed_names)
        hint = ", ".join(allowed[:hint_max])
        ellipsis = "…" if len(allowed) > hint_max else ""
        return ToolResult(
            id=tc.id,
            name=tc.name,
            content=msgf(
                "agent",
                "tool_not_allowed",
                name=tc.name,
                allowed=hint,
                ellipsis=ellipsis,
            ),
        )
    try:
        tool = registry.get(tc.name)
        result = await tool.handler(**tc.arguments, ctx=ctx)
        content = result if isinstance(result, str) else str(result)
        # Do not log tool output body (PII); name and size only.
        log.info("tool %s ok (%d chars)", tc.name, len(content))
        return ToolResult(id=tc.id, name=tc.name, content=content)
    except Exception as e:
        log.exception("tool %s failed", tc.name)
        from shared.i18n import msgf

        return ToolResult(
            id=tc.id,
            name=tc.name,
            content=msgf("agent", "tool_error", name=tc.name, error=e),
        )


async def run_agent(
    ctx: AgentContext,
    registry: ToolRegistry,
    router: ModelRouter,
    *,
    max_iters: int | None = None,
    role: ModelRole = ModelRole.ANALYZE,
    agent_progress: AgentProgress | None = None,
) -> str:
    limit = max_iters if max_iters is not None else _max_iters()
    progress = agent_progress
    if progress is None:
        raw = ctx.extras.get("agent_progress")
        progress = raw if isinstance(raw, AgentProgress) else NullAgentProgress()

    selected = await select_tools(ctx.question, registry, domain=ctx.domain)
    schemas = registry.schemas(selected)
    log.info("agent tools selected: %s", selected)
    await progress.on_tools_selected(selected)

    from shared.agent.trace import start_run
    import time as _time

    trace = start_run(user_id=ctx.user_id, domain=ctx.domain, question=ctx.question or "")
    if trace is not None:
        trace.selected_tools = list(selected)

    api_messages: list[dict[str, Any]] = [
        {"role": "system", "content": ctx.system_prompt},
        *agent_messages_to_api(ctx.history),
        {"role": "user", "content": ctx.question},
    ]

    from shared.llm_defaults import role_temperature

    loop_temp = role_temperature("analyze")

    last_text: str | None = None
    tool_bodies: list[str] = []
    tool_calls_used = 0
    from shared.agent.platform_config import platform_int

    max_tool_calls = platform_int("agent", "max_tool_calls", default=0)
    for iteration in range(limit):
        from shared.agent.config import tools_first_iter_domains

        tool_choice = (
            "required"
            if iteration == 0 and ctx.domain in tools_first_iter_domains() and schemas
            else "auto"
        )
        if max_tool_calls and tool_calls_used >= max_tool_calls:
            tool_choice = "none"
        on_delta = None
        if answer_stream_enabled() and tool_choice != "required":
            loop = asyncio.get_running_loop()

            def on_delta(text: str) -> None:
                loop.call_soon_threadsafe(
                    lambda t=text: asyncio.create_task(progress.on_answer_delta(t))
                )

        _t0 = _time.perf_counter()
        resp: LLMResponse = await router.chat_with_tools(
            api_messages,
            schemas,
            role=role,
            temperature=loop_temp,
            tool_choice=tool_choice,
            on_text_delta=on_delta,
        )
        if trace is not None:
            usage = (resp.raw or {}).get("usage") if isinstance(resp.raw, dict) else None
            model = ""
            if isinstance(resp.raw, dict):
                model = str(resp.raw.get("model") or "")
            trace.add_llm(
                iteration=iteration,
                latency_ms=(_time.perf_counter() - _t0) * 1000.0,
                model=model,
                usage=usage if isinstance(usage, dict) else None,
                tool_calls=len(resp.tool_calls or []),
            )
        if resp.text:
            last_text = resp.text

        if not resp.tool_calls:
            if resp.text:
                final = resp.text.strip()
                _warn_ungrounded_currency(final, tool_bodies)
                if trace is not None:
                    trace.finish(reason="answer", answer=final)
                return final
            from shared.i18n import msg

            out = last_text or msg("agent", "no_answer")
            if last_text:
                _warn_ungrounded_currency(out, tool_bodies)
            if trace is not None:
                trace.finish(reason="no_answer", answer=out)
            return out

        calls = parse_tool_calls(resp.tool_calls)
        if max_tool_calls and tool_calls_used + len(calls) > max_tool_calls:
            keep = max(0, max_tool_calls - tool_calls_used)
            if keep <= 0:
                if resp.text:
                    final = resp.text.strip()
                    _warn_ungrounded_currency(final, tool_bodies)
                    if trace is not None:
                        trace.finish(reason="tool_budget", answer=final)
                    return final
                break
            log.info(
                "agent tool-call budget: truncating %s -> %s (max=%s)",
                len(calls),
                keep,
                max_tool_calls,
            )
            calls = calls[:keep]
        api_messages.append(
            {
                "role": "assistant",
                "content": resp.text,
                "tool_calls": resp.tool_calls,
            }
        )

        allowed = set(selected)
        results: list[ToolResult] = []
        parallel_batch: list[Any] = []

        async def _flush_parallel() -> None:
            nonlocal parallel_batch
            if not parallel_batch:
                return
            results.extend(await asyncio.gather(*parallel_batch))
            parallel_batch = []

        for tc in calls:
            # Unknown names must not KeyError before execute_tool's allowlist/error path.
            is_serial = registry.has(tc.name) and registry.get(tc.name).serial
            if is_serial:
                await _flush_parallel()
                results.append(await execute_tool(tc, registry, ctx, allowed_names=allowed))
            else:
                parallel_batch.append(
                    execute_tool(tc, registry, ctx, allowed_names=allowed)
                )
        await _flush_parallel()
        tool_calls_used += len(calls)
        for tr in results:
            tool_bodies.append(tr.content or "")
            api_messages.append(
                {"role": "tool", "tool_call_id": tr.id, "content": tr.content}
            )
        names = [c.name for c in calls]
        log.info("agent iter %s: tools=%s", iteration + 1, names)
        await progress.on_tool_iteration(iteration + 1, names)
        if trace is not None:
            trace.add_tools(iteration=iteration + 1, names=names)

    from shared.i18n import msg

    out = last_text or msg("agent", "max_iters_reached")
    if last_text:
        _warn_ungrounded_currency(out, tool_bodies)
    if trace is not None:
        trace.finish(reason="max_iters", answer=out)
    return out
