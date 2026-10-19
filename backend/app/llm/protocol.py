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
    pass
