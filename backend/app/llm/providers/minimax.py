from app.llm.openai_compatible import OpenAICompatibleLLM


class MiniMaxLLM(OpenAICompatibleLLM):
    """MiniMax OpenAI-compatible transport."""

    # M3.1 reasoning is always enabled. Low effort is enough for the two
    # tightly-scoped JSON classification steps and leaves room for final JSON.
    reasoning_effort = "low"
