from app.config import Settings
from app.llm.fake import FakeLLM
from app.llm.protocol import LLM
from app.llm.providers.anthropic import AnthropicLLM
from app.llm.providers.azure import AzureLLM
from app.llm.providers.minimax import MiniMaxLLM
from app.llm.providers.openai import OpenAILLM
from app.llm.providers.university import UniversityLLM


def build_llm(settings: Settings) -> LLM:
    if settings.llm == "fake":
        return FakeLLM(settings.fixtures_dir / "llm")
    if settings.llm == "university":
        if not settings.ai_base_url or not settings.ai_api_key:
            raise ValueError("university requires MARKER_AI_BASE_URL and MARKER_AI_API_KEY")
        return UniversityLLM(
            settings.ai_base_url,
            settings.ai_api_key,
            settings.ai_model,
            settings.ai_timeout_seconds,
        )
    if settings.llm in {"azure", "minimax", "openai"}:
        if not settings.ai_base_url or not settings.ai_api_key:
            raise ValueError(f"{settings.llm} requires MARKER_AI_BASE_URL and MARKER_AI_API_KEY")
        adapters = {"azure": AzureLLM, "minimax": MiniMaxLLM, "openai": OpenAILLM}
        return adapters[settings.llm](
            settings.ai_base_url,
            settings.ai_api_key,
            settings.ai_model,
            settings.ai_timeout_seconds,
        )
    if settings.llm == "anthropic":
        return AnthropicLLM()
    raise ValueError(f"Unknown MARKER_LLM provider: {settings.llm}")
