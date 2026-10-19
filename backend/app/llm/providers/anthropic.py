from __future__ import annotations

from typing import Mapping, Sequence

from app.llm.protocol import LLMResponse


class AnthropicLLM:
    async def list_models(self) -> Sequence[str]:
        raise NotImplementedError("TODO(llm): implement Anthropic provider; see DEV-GUIDE §G4")

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        del purpose, prompt, metadata
        raise NotImplementedError("TODO(llm): implement Anthropic provider; see DEV-GUIDE §G4")
