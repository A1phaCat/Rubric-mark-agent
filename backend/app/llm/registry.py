from app.config import Settings
from app.llm.fake import FakeLLM
from app.llm.protocol import LLM
from app.llm.providers.anthropic import AnthropicLLM
from app.llm.providers.azure import AzureLLM
from app.llm.providers.minimax import MiniMaxLLM
from app.llm.providers.openai import OpenAILLM
from app.llm.providers.university import UniversityLLM
from app.llm.ratelimit import provider_gate


def _retry_policy(settings: Settings) -> dict:
    return {
        "max_retries": settings.llm_max_retries,
        "max_backoff_seconds": settings.llm_max_backoff_seconds,
        "gate": provider_gate(settings.llm_max_in_flight),
    }


def build_llm(settings: Settings) -> LLM:
    if settings.llm == "fake":
        if not settings.fake_llm_allowed:
            raise ValueError("The offline FakeLLM is available only when MARKER_ENV=test")
        return FakeLLM()
    if settings.llm == "university":
        if not settings.ai_base_url or not settings.ai_api_key:
            raise ValueError("university requires MARKER_AI_BASE_URL and MARKER_AI_API_KEY")
        return UniversityLLM(
            settings.ai_base_url,
            settings.ai_api_key,
            settings.ai_model,
            settings.ai_timeout_seconds,
            **_retry_policy(settings),
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
            **_retry_policy(settings),
        )
    if settings.llm == "anthropic":
        return AnthropicLLM()
    raise ValueError(f"Unknown MARKER_LLM provider: {settings.llm}")
