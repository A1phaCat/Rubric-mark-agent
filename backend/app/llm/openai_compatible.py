from __future__ import annotations

from typing import Mapping, Sequence

import httpx

from app.llm.protocol import LLMResponse, ProviderError


def response_text(choice: Mapping[str, object]) -> str:
    """Return text across common OpenAI-compatible response variants."""

    raw_message = choice.get("message")
    message = raw_message if isinstance(raw_message, dict) else {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        # MiniMax reasoning models can put the final JSON in
        # reasoning_content when a compatible gateway omits content.
        content = message.get("reasoning_content") or choice.get("text")
    return content.strip() if isinstance(content, str) else ""


class OpenAICompatibleLLM:
    def __init__(
        self, base_url: str, api_key: str, model: str, timeout_seconds: float = 120.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def list_models(self) -> Sequence[str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers)
                response.raise_for_status()
                return [item["id"] for item in response.json().get("data", [])]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            message = str(exc).strip() or "request failed"
            raise ProviderError(f"{type(exc).__name__}: {message}") from exc

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        del metadata
        output_limits = {
            "rubric_parse": 8000,
            "evidence_gate": 3500,
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
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=self._headers, json=payload
                )
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                choice = data["choices"][0]
                content = response_text(choice)
                if not content:
                    finish_reason = choice.get("finish_reason") or "unknown"
                    raise ProviderError(
                        f"Provider returned no text content (finish_reason={finish_reason})"
                    )
                return LLMResponse(
                    text=content,
                    model=data.get("model", self.model),
                    input_tokens=int(usage.get("prompt_tokens", 0)),
                    output_tokens=int(usage.get("completion_tokens", 0)),
                )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            message = str(exc).strip() or "request failed"
            raise ProviderError(f"{type(exc).__name__}: {message}") from exc
