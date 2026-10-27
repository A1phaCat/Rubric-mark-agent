from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


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
