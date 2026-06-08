"""Unified LLM client (DeepSeek-compatible) for all monorepo bots.

Merges three historical versions:
  - planning_bot/core/llm.py   (env: DEEPSEEK_API_TOKEN, hardcoded URL)
  - knowledge_bot/core/llm.py  (env: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, fallback)
  - finance_bot/bot/llm.py     (config from llm_config.yaml)

Unification:
  - api_key: explicit arg → DEEPSEEK_API_KEY → DEEPSEEK_API_TOKEN (both names)
  - base_url: explicit arg → DEEPSEEK_BASE_URL → https://api.deepseek.com/v1
  - chat_json (JSON-mode) and chat (plain text) with graceful fallback
  - is_reachable() — DNS preflight (from shared.llm_reachable)

Domain business logic (note fallback routing etc.) is NOT moved here —
stays in bots. Fallback here is maximally neutral.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional

import requests

from shared.constants import deepseek_base_url, deepseek_chat_completions_url, deepseek_model
from shared.json_parse import LLMJsonParseError, parse_json_object
from shared.llm_defaults import role_temperature, role_timeout_sec, role_tool_choice
from shared.llm_reachable import deepseek_api_reachable

log = logging.getLogger("shared.llm")

_JSON_MODE_HINT = (
    "\n\nRespond with a single valid JSON object only (no markdown fences, no extra text)."
)


def _ensure_json_in_prompt(text: str) -> str:
    """DeepSeek requires the word 'json' when response_format=json_object."""
    if not text:
        return "Return valid JSON."
    if "json" in text.lower():
        return text
    return text.rstrip() + _JSON_MODE_HINT


@dataclass
class LLMResult:
    content: Any


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[dict[str, Any]]
    raw: dict[str, Any]


def _resolve_api_key(explicit: str | None) -> str | None:
    return (
        explicit
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("DEEPSEEK_API_TOKEN")
    )


def _resolve_base_url(explicit: str | None) -> str:
    return deepseek_base_url(override=explicit)


class LLMClient:
    """DeepSeek-compatible client.

    chat_json / chat_json_messages: when raise_on_error=True — HTTP and JSON parsing raise.
    Else network errors → fallback_fn; bad JSON → {"_llm_error": "json_parse", ...}
    (do not echo user_prompt — broke brain_query and masked truncated responses).

    Extension points:
      - fallback_fn(user_prompt) -> Any
      - http_error_hook(status, body)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        *,
        fallback_fn: Optional[Callable[[str], Any]] = None,
        http_error_hook: Optional[Callable[[int, str], None]] = None,
    ):
        self.api_key = _resolve_api_key(api_key)
        self.base_url = _resolve_base_url(base_url)
        self.model = deepseek_model(override=model)
        self._fallback_fn = fallback_fn
        self._http_error_hook = http_error_hook

    # ── JSON-mode ────────────────────────────────────────────────────────────
    def _parse_chat_completion_json(
        self,
        data: dict[str, Any],
        *,
        label: str,
    ) -> dict[str, Any]:
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = str(msg.get("content") or "")
        finish = choice.get("finish_reason")
        usage = data.get("usage") or {}
        if finish and finish != "stop":
            log.error(
                "%s: finish_reason=%s completion_tokens=%s response_chars=%d",
                label,
                finish,
                usage.get("completion_tokens"),
                len(text),
            )
        try:
            return parse_json_object(text, finish_reason=finish)
        except LLMJsonParseError as e:
            log.error(
                "%s: JSON parse failed truncated=%s preview=%r",
                label,
                e.truncated,
                (e.raw_preview or text[:300]),
            )
            raise

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
        *,
        fallback: Callable[[str], Any] | None = None,
        raise_on_error: bool = False,
    ) -> LLMResult:
        model = model or self.model
        temperature = role_temperature("parse", override=temperature)
        timeout = role_timeout_sec("parse", override=timeout)
        if not self.api_key:
            log.warning("DEEPSEEK API key missing — using fallback (chat_json)")
            if raise_on_error:
                raise ValueError("DEEPSEEK API key missing")
            return LLMResult(content=self._make_fallback(user_prompt, fallback))
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": _ensure_json_in_prompt(system_prompt)},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            data = self._post(payload, timeout)
            return LLMResult(
                content=self._parse_chat_completion_json(data, label="chat_json")
            )
        except LLMJsonParseError:
            if raise_on_error:
                raise
            return LLMResult(content=self._json_parse_failure_payload())
        except Exception:
            log.exception("chat_json request failed")
            if raise_on_error:
                raise
            return LLMResult(content=self._make_fallback(user_prompt, fallback))

    # ── OpenAI-style messages (planning, finance) ───────────────────────────
    def chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
        raise_on_error: bool = False,
        max_retries: int = 1,
        retry_backoff: float = 2.0,
    ) -> str:
        """Chat with message list. Optional retry when raise_on_error."""
        from time import sleep

        model = model or self.model
        temperature = role_temperature("chat", override=temperature)
        timeout = role_timeout_sec("chat", override=timeout)
        if not self.api_key:
            if raise_on_error:
                raise ValueError("DEEPSEEK API key missing")
            return ""
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            try:
                data = self._post(payload, timeout)
                return str(data["choices"][0]["message"]["content"])
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    sleep(retry_backoff * attempt)
                    continue
                if raise_on_error:
                    raise
                log.exception("chat_messages failed after %s attempts", attempt)
                return ""
        if raise_on_error and last_exc:
            raise last_exc
        return ""

    def chat_json_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        """JSON-mode with message list. On error — {} or raise."""
        model = model or self.model
        temperature = role_temperature("parse", override=temperature)
        timeout = role_timeout_sec("parse", override=timeout)
        if not self.api_key:
            if raise_on_error:
                raise ValueError("DEEPSEEK API key missing")
            return {}
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {**m, "content": _ensure_json_in_prompt(m["content"])} if m.get("role") == "system" and isinstance(m.get("content"), str) else m
                for m in messages
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            data = self._post(payload, timeout)
            return self._parse_chat_completion_json(data, label="chat_json_messages")
        except LLMJsonParseError:
            if raise_on_error:
                raise
            log.error("chat_json_messages: parse failed — returning error marker")
            return self._json_parse_failure_payload()
        except Exception:
            if raise_on_error:
                raise
            log.exception("chat_json_messages request failed")
            return {}

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        tool_choice: str | None = None,
        timeout: float | None = None,
        raise_on_error: bool = False,
    ) -> LLMResponse:
        """OpenAI-compatible function calling."""
        model = model or self.model
        temperature = role_temperature("analyze", override=temperature)
        tool_choice = role_tool_choice("analyze", override=tool_choice)
        timeout = role_timeout_sec("analyze", override=timeout)
        if not self.api_key:
            msg = "DEEPSEEK API key missing"
            if raise_on_error:
                raise ValueError(msg)
            log.warning("%s — chat_with_tools empty response", msg)
            return LLMResponse(text=None, tool_calls=[], raw={})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
        }
        try:
            data = self._post(payload, timeout)
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            text = msg.get("content")
            tool_calls = msg.get("tool_calls") or []
            usage = data.get("usage")
            if usage:
                log.info(
                    "LLM tools usage: prompt=%s completion=%s total=%s",
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("total_tokens"),
                )
            return LLMResponse(text=text, tool_calls=tool_calls, raw=data)
        except Exception:
            log.exception("chat_with_tools failed")
            if raise_on_error:
                raise
            return LLMResponse(text=None, tool_calls=[], raw={})

    def chat_with_tools_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        tool_choice: str | None = None,
        timeout: float | None = None,
        raise_on_error: bool = False,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Streaming chat/completions; on_text_delta — accumulated text (only when no tool_calls)."""
        model = model or self.model
        temperature = role_temperature("analyze", override=temperature)
        tool_choice = role_tool_choice("analyze", override=tool_choice)
        timeout = role_timeout_sec("analyze", override=timeout)
        if not self.api_key:
            msg = "DEEPSEEK API key missing"
            if raise_on_error:
                raise ValueError(msg)
            log.warning("%s — chat_with_tools_stream empty response", msg)
            return LLMResponse(text=None, tool_calls=[], raw={})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
            "stream": True,
        }
        try:
            text, tool_calls = self._stream_chat_completion(
                payload, timeout, on_text_delta=on_text_delta
            )
            return LLMResponse(text=text, tool_calls=tool_calls, raw={})
        except Exception:
            log.exception("chat_with_tools_stream failed")
            if raise_on_error:
                raise
            return LLMResponse(text=None, tool_calls=[], raw={})

    def _stream_chat_completion(
        self,
        payload: dict[str, Any],
        timeout: float,
        *,
        on_text_delta: Callable[[str], None] | None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        url = deepseek_chat_completions_url(override=self.base_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        log.info("LLM stream: url=%s model=%s", url, payload.get("model"))
        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=timeout,
            stream=True,
        )
        if not resp.ok:
            if self._http_error_hook is not None:
                try:
                    self._http_error_hook(resp.status_code, resp.text or "")
                except Exception:
                    log.exception("http_error_hook failed")
            log.error("LLM HTTP %s: %s", resp.status_code, (resp.text or "")[:300])
            resp.raise_for_status()

        text_parts: list[str] = []
        tool_acc: dict[int, dict[str, Any]] = {}
        for line in self._iter_sse_data_lines(resp):
            if line == "[DONE]":
                break
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                text_parts.append(str(delta["content"]))
                if on_text_delta and not tool_acc:
                    on_text_delta("".join(text_parts))
            for tc in delta.get("tool_calls") or []:
                idx = int(tc.get("index", 0))
                slot = tool_acc.setdefault(
                    idx,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]

        tool_calls = [tool_acc[i] for i in sorted(tool_acc)]
        text = "".join(text_parts) if text_parts else None
        if tool_calls and on_text_delta:
            pass  # do not stream answer when model chose tools
        return text, tool_calls

    @staticmethod
    def _iter_sse_data_lines(resp: requests.Response) -> Iterator[str]:
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            yield raw[6:].strip()

    # ── Plain text ───────────────────────────────────────────────────────────
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        model = model or self.model
        temperature = role_temperature("chat", override=temperature)
        timeout = role_timeout_sec("chat", override=timeout)
        if not self.api_key:
            log.warning("DEEPSEEK API key missing — echo input (chat)")
            return LLMResult(content=user_prompt)
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
            data = self._post(
                {"model": model, "messages": messages, "temperature": temperature},
                timeout,
            )
            return LLMResult(content=data["choices"][0]["message"]["content"])
        except Exception as e:
            log.warning("chat failed (%s) — echo input", e)
            return LLMResult(content=user_prompt)

    # ── Internal ──────────────────────────────────────────────────────────────
    def _post(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        url = deepseek_chat_completions_url(override=self.base_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        log.info("LLM request: url=%s model=%s", url, payload.get("model"))
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        if not resp.ok:
            if self._http_error_hook is not None:
                try:
                    self._http_error_hook(resp.status_code, resp.text or "")
                except Exception:
                    log.exception("http_error_hook failed")
            log.error("LLM HTTP %s: %s", resp.status_code, (resp.text or "")[:300])
            resp.raise_for_status()
        return resp.json()

    def _make_fallback(self, user_prompt: str, fn: Callable[[str], Any] | None = None) -> Any:
        """Order: per-call fn → instance fallback_fn → overridable _fallback."""
        cb = fn or self._fallback_fn
        if cb is not None:
            try:
                return cb(user_prompt)
            except Exception:
                log.exception("fallback callback failed")
        return self._fallback(user_prompt)

    @staticmethod
    def _json_parse_failure_payload() -> dict[str, Any]:
        return {
            "_llm_error": "json_parse",
            "error": "llm_json_invalid",
        }

    def _fallback(self, user_prompt: str) -> Any:
        """Neutral fallback. Subclasses may override for their domain."""
        return {"error": "llm_unavailable"}

    @staticmethod
    def is_reachable(timeout: float | None = None) -> bool:
        return deepseek_api_reachable(timeout)
