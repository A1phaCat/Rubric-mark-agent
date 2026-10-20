import asyncio
from collections.abc import Mapping, Sequence

from app.grading.service import _complete_json, _json_object
from app.llm.protocol import LLMResponse


class RepairingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def list_models(self) -> Sequence[str]:
        return []

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        del purpose, prompt
        self.calls += 1
        if self.calls == 1:
            return LLMResponse("The criterion is mostly satisfied.", "test", 10, 4)
        assert metadata and metadata.get("repair") == "true"
        return LLMResponse(
            '{"score": 1.5, "level": "Good", "rationale": "Relevant", '
            '"confidence": "high"}',
            "test",
            6,
            3,
        )


def test_complete_json_repairs_prose_only_response_once() -> None:
    llm = RepairingLLM()
    value, response = asyncio.run(
        _complete_json(
            llm,
            purpose="criterion_grade",
            prompt="Return JSON",
            metadata={"submission_id": "sub_test"},
        )
    )

    assert value == {
        "score": 1.5,
        "level": "Good",
        "rationale": "Relevant",
        "confidence": "high",
    }
    assert response.input_tokens == 16
    assert response.output_tokens == 7
    assert llm.calls == 2


def test_json_object_accepts_trailing_prose_and_another_object() -> None:
    value = _json_object('Result:\n{"score": 2, "level": "Good"}\nExplanation {"ignored": true}')

    assert value == {"score": 2, "level": "Good"}


def test_json_object_prefers_final_object_matching_the_required_schema() -> None:
    value = _json_object(
        '{"rubric": "prompt echo"}\n'
        '{"evidence": [{"passage_id": "example"}]}\n'
        '{"evidence": [], "notes": "final answer"}',
        required_keys=frozenset({"evidence"}),
    )

    assert value == {"evidence": [], "notes": "final answer"}
