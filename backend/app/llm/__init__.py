"""Provider-neutral model access. Only this package may call model providers."""

from app.llm.protocol import LLM, LLMResponse
from app.llm.registry import build_llm

__all__ = ["LLM", "LLMResponse", "build_llm"]
