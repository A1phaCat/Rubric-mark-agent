"""Named provider adapters; all expose the common LLM Protocol."""

from app.llm.fake import FakeLLM
from app.llm.providers.anthropic import AnthropicLLM
from app.llm.providers.azure import AzureLLM
from app.llm.providers.minimax import MiniMaxLLM
from app.llm.providers.openai import OpenAILLM

__all__ = ["FakeLLM", "AzureLLM", "MiniMaxLLM", "OpenAILLM", "AnthropicLLM"]
