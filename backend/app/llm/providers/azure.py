from app.llm.openai_compatible import OpenAICompatibleLLM


class AzureLLM(OpenAICompatibleLLM):
    """Azure/OpenAI-compatible transport; deployment URL is supplied by settings."""
