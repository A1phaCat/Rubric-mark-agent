from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence, TypeVar

import httpx

from app.llm.protocol import (
    ChatResponse,
    FatalProviderError,
    LLMResponse,
    ProviderError,
    RetryableProviderError,
    ToolSpec,
    parse_tool_call,
)
from app.llm.ratelimit import ProviderGate, provider_gate

# 408 timeout, 409 conflict, 425 too early, 429 rate limit, 5xx overload; 529 = "overloaded".
_RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})
_GLOBAL_PAUSE_STATUS = frozenset({429, 503, 529})
_MAX_RETRY_AFTER_SECONDS = 300.0
T = TypeVar("T")
_CONTEXT_LENGTH = re.compile(
    r"context[_ ]length|maximum context|too many tokens|prompt is too long|input is too long|"
    r"exceeds? the (?:model'?s )?(?:context|token limit)",
    re.IGNORECASE,
)


def retry_after_seconds(headers: Mapping[str, str], now: datetime | None = None) -> float | None:
    """Seconds to wait from ``Retry-After`` (seconds or HTTP date) or ``retry-after-ms``."""

    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    if lowered.get("retry-after-ms"):
        try:
            return max(0.0, float(lowered["retry-after-ms"]) / 1000)
        except ValueError:
            pass
    value = lowered.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (moment - (now or datetime.now(timezone.utc))).total_seconds())


def _status_error(response: httpx.Response) -> ProviderError:
    detail = response.text[:300].strip()
    message = f"HTTP {response.status_code}" + (f": {detail}" if detail else "")
    if response.status_code in _RETRYABLE_STATUS:
        return RetryableProviderError(
            message, retry_after=retry_after_seconds(response.headers), status=response.status_code
        )
    reason = "context_length" if _CONTEXT_LENGTH.search(detail) else None
    return FatalProviderError(message, status=response.status_code, reason=reason)


def response_text(choice: Mapping[str, object]) -> str:
    """Return text across common OpenAI-compatible response variants."""

    raw_message = choice.get("message")
    message = raw_message if isinstance(raw_message, dict) else {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "") for part in content if isinstance(part, dict)
        )
    reasoning = message.get("reasoning_content")
    if (
        isinstance(content, str)
        and content.strip()
        and "{" not in content
        and isinstance(reasoning, str)
        and "{" in reasoning
    ):
        content = reasoning
    if not isinstance(content, str) or not content.strip():
        # MiniMax reasoning models can put the final JSON in
        # reasoning_content when a compatible gateway omits content.
        content = reasoning or choice.get("text")
    return content.strip() if isinstance(content, str) else ""


class OpenAICompatibleLLM:
    reasoning_effort: str | None = None

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        *,
        max_retries: int = 5,
        max_backoff_seconds: float = 60.0,
        gate: ProviderGate | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self.max_backoff_seconds = float(max_backoff_seconds)
        self.gate = gate or provider_gate(6)
        self.retries = 0  # retries made by this client, for tests and diagnostics
        self._transport = transport  # tests only

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def list_models(self) -> Sequence[str]:
        try:
            async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers)
                if response.status_code >= 400:
                    raise _status_error(response)
                return [item["id"] for item in response.json().get("data", [])]
        except ProviderError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            message = str(exc).strip() or "request failed"
            raise ProviderError(f"{type(exc).__name__}: {message}") from exc

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        del metadata
        output_limits = {
            "rubric_parse": 8000,
            "evidence_gate": 6000,
            # Reasoning-capable OpenAI-compatible models count their hidden
            # reasoning in the completion budget.  A small budget can finish
            # before the final JSON reaches message.content.
            "criterion_grade": 4000,
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": output_limits.get(purpose, 2500),
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return await self._with_retries(lambda: self._complete_once(payload))

    async def chat(
        self,
        *,
        purpose: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        metadata: Mapping[str, str] | None = None,
    ) -> ChatResponse:
        del metadata
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "tools": [tool.as_openai() for tool in tools],
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": 4000 if purpose == "evidence_check" else 2500,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return await self._with_retries(lambda: self._chat_once(payload))

    async def _with_retries(self, send: Callable[[], Awaitable[T]]) -> T:
        """Run one provider call behind the shared gate, retrying what waiting can fix."""

        attempt = 0
        while True:
            try:
                async with self.gate.slot():
                    return await send()
            except RetryableProviderError as exc:
                if attempt >= self.max_retries:
                    raise RetryableProviderError(
                        f"{exc} (gave up after {attempt + 1} attempts)",
                        retry_after=exc.retry_after,
                        status=exc.status,
                    ) from exc
                wait = self._backoff(attempt, exc.retry_after)
                if exc.retry_after is not None and exc.retry_after > _MAX_RETRY_AFTER_SECONDS:
                    raise RetryableProviderError(
                        f"{exc} (provider asked to wait {exc.retry_after:.0f} s)",
                        retry_after=exc.retry_after,
                        status=exc.status,
                    ) from exc
                if exc.status in _GLOBAL_PAUSE_STATUS:
                    self.gate.cool_down(wait)  # every slot waits, not only this call
                attempt += 1
                self.retries += 1
                await asyncio.sleep(wait)

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, _MAX_RETRY_AFTER_SECONDS)
        base = min(self.max_backoff_seconds, 2.0 ** attempt)
        return base * random.uniform(0.5, 1.0)

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self._transport) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=self._headers, json=payload
                )
                if response.status_code >= 400:
                    raise _status_error(response)
                data = response.json()
                if not isinstance(data, dict) or not data.get("choices"):
                    raise ValueError("response has no choices")
                return data
        except ProviderError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            message = str(exc).strip() or "request failed"
            raise RetryableProviderError(f"{type(exc).__name__}: {message}") from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            message = str(exc).strip() or "request failed"
            raise ProviderError(f"{type(exc).__name__}: {message}") from exc

    async def _complete_once(self, payload: dict[str, Any]) -> LLMResponse:
        data = await self._request(payload)
        choice = data["choices"][0]
        content = response_text(choice)
        if not content:
            _raise_empty(choice)
        input_tokens, output_tokens, cached = _usage(data)
        return LLMResponse(
            text=content,
            model=data.get("model", self.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached,
        )

    async def _chat_once(self, payload: dict[str, Any]) -> ChatResponse:
        started = time.perf_counter()
        data = await self._request(payload)
        choice = data["choices"][0]
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        calls = tuple(
            parse_tool_call(index, raw)
            for index, raw in enumerate(message.get("tool_calls") or [])
            if isinstance(raw, dict)
        )
        text = message.get("content") if isinstance(message.get("content"), str) else ""
        if not calls and not (text or "").strip():
            _raise_empty(choice)
        input_tokens, output_tokens, cached = _usage(data)
        return ChatResponse(
            text=(text or "").strip(),
            tool_calls=calls,
            model=data.get("model", self.model),
            finish_reason=str(choice.get("finish_reason") or ""),
            reasoning=str(message.get("reasoning_content") or ""),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _usage(data: Mapping[str, Any]) -> tuple[int, int, int]:
    usage = data.get("usage") if isinstance(data.get("usage"), Mapping) else {}
    details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), Mapping) else {}
    return (
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
        int(details.get("cached_tokens") or 0),
    )


def _raise_empty(choice: Mapping[str, Any]) -> None:
    finish_reason = choice.get("finish_reason") or "unknown"
    message = f"Provider returned no text content (finish_reason={finish_reason})"
    if finish_reason == "length":
        # Deterministic at temperature 0: the output budget is too small.
        raise FatalProviderError(message)
    raise RetryableProviderError(message)
