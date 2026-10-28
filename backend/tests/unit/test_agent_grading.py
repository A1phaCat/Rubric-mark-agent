"""The tool-based evidence check inside grading: what reaches the grade, the record kept, fallback."""

import asyncio
import json

import pytest
from sqlalchemy import select

from app.config import Settings
from app.config import settings as app_settings
from app.db.models.batch import Batch
from app.db.models.llm import LLMCall
from app.db.models.submission import AIResult, Evidence, Submission
from app.grading import service as grading
from app.grading.service import grade_criterion
from app.llm.protocol import ChatResponse, FatalProviderError, LLMResponse, ToolCall
from app.retrieval import full_document
from app.services.grading_service import grade_submission
from tests.unit.test_full_text_grading import _criterion, _document, stored  # noqa: F401

GRADE = {"score": 10, "level": "Good", "rationale": "Measured and reported.", "confidence": "high"}


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(id=f"{name}_{len(arguments)}", name=name, raw_arguments=json.dumps(arguments), arguments=arguments)


class ToolLLM:
    """Plays back evidence-check turns, then answers the grade step."""

    def __init__(self, *turns, error: Exception | None = None, gate: dict | None = None) -> None:
        self.turns = list(turns)
        self.error = error
        self.gate = gate or {"evidence": []}
        self.purposes: list[str] = []
        self.grade_prompt = ""

    async def chat(self, *, purpose, messages, tools, metadata=None):
        self.purposes.append(purpose)
        if self.error is not None:
            raise self.error
        calls = self.turns.pop(0) if self.turns else (call("finish", notes="done"),)
        return ChatResponse(text="", tool_calls=tuple(calls), model="tools-model",
                            input_tokens=3000, output_tokens=40, cached_tokens=2500, latency_ms=900)

    async def complete(self, *, purpose, prompt, metadata=None):
        self.purposes.append(purpose)
        if purpose == "criterion_grade":
            self.grade_prompt = prompt
            return LLMResponse(json.dumps(GRADE), "tools-model", 800, 60)
        return LLMResponse(json.dumps(self.gate), "tools-model", 3000, 200)


class CompleteOnly(ToolLLM):
    chat = None  # a provider adapter without tool calling


MEASURED = call("cite", paragraph_id="p4", quote="We measured latency under load", aspect_ids=["measures", "reports"],
                relevance="direct")


def _run(llm, **settings):
    full = full_document(_document())
    configured = Settings(llm="minimax", grading_context="full_tools", **settings)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(grading, "build_llm", lambda _settings: llm)
        return asyncio.run(grade_criterion(configured, _criterion(), full.passages, {}, full=full))


def test_the_check_feeds_the_unchanged_grade_step() -> None:
    llm = ToolLLM((MEASURED,), (call("finish", notes="all found"),))
    result = _run(llm)
    assert llm.purposes == ["evidence_check", "evidence_check", "criterion_grade"]
    assert result["context"] == "full_tools"
    assert [e["quote"] for e in result["evidence"]] == ["We measured latency under load"]
    assert "We measured latency" in llm.grade_prompt and "Lee, K. (2021)" not in llm.grade_prompt
    assert (result["score"], result["level"]) == (10, "Good")


def test_the_steps_and_every_provider_call_are_kept() -> None:
    result = _run(ToolLLM((MEASURED,), (call("finish", notes="all found"),)))
    kinds = [step["kind"] for step in result["evidence_trace"]]
    assert kinds == ["read", "model", "tool", "model", "tool"]
    assert [c["purpose"] for c in result["llm_calls"]] == ["evidence_check", "evidence_check", "criterion_grade"]
    assert (result["input_tokens"], result["cached_tokens"]) == (6800, 5000)


def test_a_provider_without_tool_calling_reads_in_one_pass() -> None:
    gate = {"evidence": [{"passage_id": "p4", "quote": "We measured latency under load", "role": "primary",
                          "relevance": "direct", "aspect_ids": ["measures", "reports"]}]}
    llm = CompleteOnly(gate=gate)
    result = _run(llm)
    assert llm.purposes == ["evidence_gate", "criterion_grade"]
    assert result["context"] == "full"
    assert result["evidence_trace"][-1]["kind"] == "fallback"
    assert "does not support tool calling" in result["evidence_trace"][-1]["detail"]


def test_a_rejected_tool_request_falls_back_to_one_pass() -> None:
    llm = ToolLLM(error=FatalProviderError("HTTP 400: tools are not supported", status=400))
    result = _run(llm)
    assert llm.purposes == ["evidence_check", "evidence_gate"]  # no evidence: no grade call
    assert result["context"] == "full" and result["evidence_trace"][-1]["kind"] == "fallback"


@pytest.mark.parametrize("error", [
    FatalProviderError("HTTP 401: invalid key", status=401),
    FatalProviderError("HTTP 400: maximum context length", status=400, reason="context_length"),
])
def test_wrong_keys_and_over_long_submissions_are_not_hidden_by_the_fallback(error) -> None:
    with pytest.raises(FatalProviderError):
        _run(ToolLLM(error=error))


def test_a_check_that_never_answers_is_read_again_in_one_pass() -> None:
    endless = tuple((call("search", query="latency"),) for _ in range(10))
    llm = ToolLLM(*endless)
    result = _run(llm, agent_max_rounds=2)
    assert llm.purposes == ["evidence_check", "evidence_check", "evidence_gate"]
    assert [step["kind"] for step in result["evidence_trace"]][-2:] == ["limit", "fallback"]


def test_the_check_is_stored_with_the_result_and_its_calls_are_logged(stored) -> None:  # noqa: F811
    settings = app_settings.model_copy(update={"llm": "fake", "grading_context": "full_tools"})

    async def go():
        with stored() as session:
            await grade_submission(session, settings, session.get(Submission, "sub_t"),
                                   session.get(Batch, "bat_t"), [_criterion()], commit_progress=True)

    asyncio.run(go())
    with stored() as session:
        result = session.scalar(select(AIResult))
        trace = json.loads(result.trace_json)
        assert result.prompt_version == "criterion-grade-fulltools-v1"
        assert json.loads(result.minor_json)["context"] == "full_tools"
        assert trace[0]["kind"] == "read" and any(step["tool"] == "cite" for step in trace)
        assert session.scalars(select(Evidence)).all()
        purposes = [row.purpose for row in session.scalars(select(LLMCall))]
        assert purposes and set(purposes) == {"evidence_check"}  # the fake grade step makes no call
