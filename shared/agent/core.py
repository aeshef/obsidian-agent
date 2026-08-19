"""Agent loop: tool selection → LLM → execute tools → repeat."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from shared.agent.router import ModelRouter
from shared.agent.tools import ToolRegistry, select_tools
from shared.agent.progress import AgentProgress, NullAgentProgress, answer_stream_enabled
from shared.agent.types import (
    AgentContext,
    AgentMessage,
    ModelRole,
    ToolCall,
    ToolResult,
    ToolSelection,
)
from shared.agent.cascade import (
    cascade_enabled,
    escalate_ungrounded_claims,
    initial_role,
    should_escalate_skipped_tools,
    strong_role,
)
from shared.agent.verify import tools_excerpt, verify_draft
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
    """History for the LLM. Clock only on user turns (local TZ) so the model
    does not imitate `[at …]` on its own replies. Never persist this prefix.
    """
    from shared.tz import format_local_ts

    out: list[dict[str, Any]] = []
    for m in messages:
        content = m.content or ""
        if m.ts and m.role == "user":
            local = format_local_ts(m.ts)
            if local:
                content = f"[asked {local}] {content}"
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


def strip_injected_history_clock(text: str) -> str:
    """Drop harness clock prefixes the model copied into a user-visible reply."""
    out = (text or "").strip()
    while True:
        if out.startswith("[at "):
            marker = "[at "
        elif out.startswith("[asked "):
            marker = "[asked "
        else:
            break
        end = out.find("]")
        if end < 0:
            break
        inner = out[len(marker) : end].strip()
        if not _looks_like_clock(inner):
            break
        out = out[end + 1 :].lstrip()
    return out


def _looks_like_clock(inner: str) -> bool:
    # YYYY-MM-DD … — harness stamps only, not prose like "[at home]".
    return len(inner) >= 10 and inner[4:5] == "-" and inner[7:8] == "-" and inner[:4].isdigit()


def _verify_retry_hint(tool_bodies: list[str]) -> str:
    from shared.i18n import msgf

    facts = tools_excerpt(tool_bodies) or "—"
    return msgf("agent", "verify_retry_hint", facts=facts)


async def _verified_answer(text: str, tool_bodies: list[str]) -> tuple[str, bool]:
    """Ground draft via LLM. Returns (text, needs_retry). Never a user-facing refuse."""
    verdict = await verify_draft(text, tool_bodies)
    if verdict.ok:
        return strip_injected_history_clock(text), False
    if verdict.rewrite:
        log.info("verify llm rewrite (%d chars)", len(verdict.rewrite))
        return strip_injected_history_clock(verdict.rewrite), False
    return strip_injected_history_clock(text), True


async def _emit_loop_model(progress: AgentProgress, router: ModelRouter, role: ModelRole) -> None:
    model = ""
    getter = getattr(router, "model_for", None)
    if callable(getter):
        try:
            model = str(getter(role) or "")
        except Exception:
            model = ""
    fn = getattr(progress, "on_loop_model", None)
    if callable(fn):
        await fn(model, role.value)


def _coerce_selection(raw: Any) -> ToolSelection:
    if isinstance(raw, ToolSelection):
        return raw
    if isinstance(raw, (list, tuple)):
        names = [str(n) for n in raw if str(n)]
        return ToolSelection(offered=names, picked=list(names))
    return ToolSelection()


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
        try:
            from shared.memory.working_set import observe_tool_output

            observe_tool_output(ctx.user_id, ctx.domain, tc.name, content)
        except Exception:
            log.debug("working_set observe_tool_output skipped", exc_info=True)
        try:
            from shared.agent.loop_context import record_tool_result

            record_tool_result(ctx, tc.name, content)
        except Exception:
            log.debug("loop_tool_results skip", exc_info=True)
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

    selection = _coerce_selection(
        await select_tools(
            ctx.question, registry, domain=ctx.domain, history=ctx.history
        )
    )
    # Pin stays in the catalog; schemas/allowlist only when this turn picked tools.
    selected = selection.offered if selection.picked else []
    schemas = registry.schemas(selected)
    log.info(
        "agent tools offered=%s picked=%s schemas=%d",
        selection.offered,
        selection.picked,
        len(schemas),
    )
    await progress.on_tools_selected(selection.picked)

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

    loop_role = role
    if cascade_enabled():
        loop_role = initial_role(ctx.domain, ctx.question)
        if role == strong_role():
            loop_role = strong_role()

    last_text: str | None = None
    tool_bodies: list[str] = []
    tool_calls_used = 0
    escalated = loop_role == strong_role()
    force_tools = False
    from shared.agent.platform_config import platform_int

    max_tool_calls = platform_int("agent", "max_tool_calls", default=0)
    for iteration in range(limit):
        from shared.agent.config import tools_first_iter_domains

        loop_temp = role_temperature(loop_role.value)
        tool_choice = (
            "required"
            if (
                force_tools
                or (
                    iteration == 0
                    and ctx.domain in tools_first_iter_domains()
                    and selection.picked
                    and schemas
                )
            )
            else "auto"
        )
        force_tools = False
        if max_tool_calls and tool_calls_used >= max_tool_calls:
            tool_choice = "none"
        on_delta = None
        if answer_stream_enabled() and tool_choice != "required":
            loop = asyncio.get_running_loop()

            def on_delta(text: str) -> None:
                from shared.agent.answer_guard import looks_like_tool_narration

                if looks_like_tool_narration(text or ""):
                    return
                loop.call_soon_threadsafe(
                    lambda t=text: asyncio.create_task(progress.on_answer_delta(t))
                )

        context_chars = 0
        for _m in api_messages:
            context_chars += len(str((_m or {}).get("content") or ""))
            # tool_calls JSON on assistant turns also inflate context
            tcs = (_m or {}).get("tool_calls")
            if tcs:
                context_chars += len(str(tcs))
        tools_schema_chars = len(str(schemas)) if schemas else 0
        if trace is not None:
            trace.note_context(
                messages_chars=context_chars, tools_schema_chars=tools_schema_chars
            )

        await _emit_loop_model(progress, router, loop_role)
        _t0 = _time.perf_counter()
        resp: LLMResponse = await router.chat_with_tools(
            api_messages,
            schemas,
            role=loop_role,
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
                context_chars=context_chars,
            )
        if resp.text:
            last_text = resp.text

        if not resp.tool_calls:
            from shared.agent.answer_guard import coerce_text_tool_calls

            coerced = coerce_text_tool_calls(resp.text or "")
            if coerced:
                log.info("agent parsed %s tool call(s) from text narration", len(coerced))
                resp = LLMResponse(text="", tool_calls=coerced, raw=resp.raw or {})

        if not resp.tool_calls:
            if resp.text:
                from shared.agent.answer_guard import (
                    looks_like_incomplete_fetch,
                    looks_like_tool_narration,
                    strip_tool_narration,
                )
                from shared.i18n import msg

                can_retry = iteration < limit - 1
                if (
                    can_retry
                    and schemas
                    and (
                        looks_like_incomplete_fetch(resp.text)
                        or looks_like_tool_narration(resp.text)
                    )
                ):
                    log.info(
                        "agent retry incomplete/narration iter=%s chars=%s",
                        iteration,
                        len(resp.text or ""),
                    )
                    api_messages.append({"role": "assistant", "content": resp.text})
                    api_messages.append(
                        {"role": "user", "content": msg("agent", "incomplete_fetch_hint")}
                    )
                    force_tools = bool(schemas)
                    continue
                final = strip_tool_narration(resp.text).strip()
                if not final:
                    if not escalated and can_retry:
                        escalated = True
                        loop_role = strong_role()
                        log.warning(
                            "cascade escalate -> %s reason=stripped_narration iter=%s",
                            loop_role.value,
                            iteration,
                        )
                        continue
                    from shared.i18n import msg

                    out = msg("agent", "no_answer")
                    if trace is not None:
                        trace.finish(reason="no_answer", answer=out)
                    return out
                can_retry = iteration < limit - 1
                final, needs_retry = await _verified_answer(final, tool_bodies)
                if needs_retry and not escalated and can_retry and escalate_ungrounded_claims():
                    escalated = True
                    loop_role = strong_role()
                    log.info("cascade escalate -> %s reason=verify", loop_role.value)
                    api_messages.append(
                        {"role": "user", "content": _verify_retry_hint(tool_bodies)}
                    )
                    continue
                if (
                    not needs_retry
                    and not escalated
                    and can_retry
                    and should_escalate_skipped_tools(
                        domain=ctx.domain,
                        had_schemas=bool(selection.picked),
                        tool_bodies=tool_bodies,
                    )
                ):
                    escalated = True
                    loop_role = strong_role()
                    log.info("cascade escalate -> %s reason=skipped_tools", loop_role.value)
                    continue
                if trace is not None:
                    trace.finish(reason="answer", answer=final)
                return final
            if not escalated and iteration < limit - 1:
                escalated = True
                loop_role = strong_role()
                log.warning(
                    "cascade escalate -> %s reason=empty_response iter=%s",
                    loop_role.value,
                    iteration,
                )
                continue
            from shared.i18n import msg

            out = last_text or msg("agent", "no_answer")
            if last_text:
                out, _needs = await _verified_answer(out, tool_bodies)
            if trace is not None:
                trace.finish(reason="no_answer", answer=out)
            return out

        calls = parse_tool_calls(resp.tool_calls)
        if max_tool_calls and tool_calls_used + len(calls) > max_tool_calls:
            keep = max(0, max_tool_calls - tool_calls_used)
            if keep <= 0:
                if resp.text:
                    final, _needs = await _verified_answer(resp.text.strip(), tool_bodies)
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
        from shared.agent.loop_context import llm_tool_content, refresh_system_working_set

        for tr in results:
            tool_bodies.append(tr.content or "")
            api_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tr.id,
                    "content": llm_tool_content(tr.content or ""),
                }
            )
        refresh_system_working_set(
            api_messages, user_id=ctx.user_id, domain=ctx.domain
        )
        try:
            from shared.agent.types import LOOP_TOOL_RESULTS_KEY
            from shared.memory.tool_facts import remember_loop_facts

            rows = ctx.extras.get(LOOP_TOOL_RESULTS_KEY) or []
            if isinstance(rows, list) and rows:
                remember_loop_facts(
                    ctx.user_id,
                    ctx.domain,
                    [
                        (str(r.get("name") or ""), str(r.get("content") or ""))
                        for r in rows
                        if isinstance(r, dict)
                    ],
                )
        except Exception:
            log.debug("tool_facts persist skipped", exc_info=True)
        names = [c.name for c in calls]
        log.info("agent iter %s: tools=%s", iteration + 1, names)
        await progress.on_tool_iteration(iteration + 1, names)
        if trace is not None:
            trace.add_tools(iteration=iteration + 1, names=names)

    from shared.i18n import msg

    out = last_text or msg("agent", "max_iters_reached")
    if last_text:
        out, _needs = await _verified_answer(out, tool_bodies)
    if trace is not None:
        trace.finish(reason="max_iters", answer=out)
    return out
