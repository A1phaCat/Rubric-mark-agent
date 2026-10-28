from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


@dataclass(frozen=True)
class ToolCall:
    """One tool call requested by the model. ``arguments`` is None when they were not valid JSON."""

    id: str
    name: str
    raw_arguments: str
    arguments: dict[str, Any] | None


@dataclass(frozen=True)
class ChatResponse:
    text: str
    tool_calls: tuple[ToolCall, ...]
    model: str
    finish_reason: str = ""
    reasoning: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: int = 0

    def as_message(self) -> dict[str, Any]:
        """The assistant turn in OpenAI chat format, to send back with the tool results."""

        message: dict[str, Any] = {"role": "assistant", "content": self.text or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.raw_arguments},
                }
                for call in self.tool_calls
            ]
        return message


def parse_tool_call(index: int, raw: Mapping[str, Any]) -> ToolCall:
    function = raw.get("function") if isinstance(raw.get("function"), Mapping) else {}
    raw_arguments = str(function.get("arguments") or "{}")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        arguments = None
    return ToolCall(
        id=str(raw.get("id") or f"call_{index}"),
        name=str(function.get("name") or ""),
        raw_arguments=raw_arguments,
        arguments=arguments if isinstance(arguments, dict) else None,
    )


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call, described with a JSON Schema for its arguments."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def as_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class LLM(Protocol):
    """Stable provider boundary; callers cannot depend on provider SDK types."""

    async def list_models(self) -> Sequence[str]:
        """Return accessible model identifiers or raise ProviderError."""
        ...

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        """Complete one prompt without side effects outside usage logging/cache."""
        ...


class ToolChatLLM(Protocol):
    """A provider that can hold a multi-turn conversation in which the model calls tools."""

    async def chat(
        self,
        *,
        purpose: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        metadata: Mapping[str, str] | None = None,
    ) -> ChatResponse:
        """One model turn: text and/or tool calls. Retries rate limits like ``complete``."""
        ...


class ProviderError(RuntimeError):
    """A provider call failed.

    ``final`` tells the job queue not to run the whole job again: the LLM client has
    already retried everything that retrying can fix.
    """

    final = True


class RetryableProviderError(ProviderError):
    """Rate limit (429), overload (5xx), timeout or dropped connection — worth waiting for."""

    def __init__(self, message: str, *, retry_after: float | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.status = status


class FatalProviderError(ProviderError):
    """Wrong key, unknown model, request too large… — the same call will fail again.

    ``reason`` is ``"context_length"`` when the prompt is longer than the model accepts.
    """

    def __init__(self, message: str, *, status: int | None = None, reason: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason
