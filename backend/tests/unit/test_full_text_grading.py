"""Full-text evidence step, verified-evidence-only grading, and the no-truncation rule."""

import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.config import settings as app_settings
from app.db.base import Base
from app.db.models.batch import Batch
from app.db.models.core import Term, User
from app.db.models.rubric import Rubric
from app.db.models.submission import Submission
from app.grading import service as grading
from app.grading.service import _FULL_GATE_HEADER, _normalise_gate, grade_criterion
from app.llm.protocol import FatalProviderError, LLMResponse
from app.retrieval import find_quote, full_document, locate_quote
from app.services import grading_service
from app.services.grading_service import DocumentTooLong, grade_submission

LONG = " ".join(f"word{i}" for i in range(400))  # one 400-word paragraph


def _document() -> dict:
    blocks = [
        {"kind": "heading", "text": "1. Introduction", "page": 1, "label": ""},
        {"kind": "paragraph", "text": "This report defines “latency” as the delay seen by a user.", "page": 1, "label": "¶1"},
        {"kind": "paragraph", "text": LONG, "page": 1, "label": "¶2"},
        {"kind": "heading", "text": "2. Method", "page": 2, "label": ""},
        {"kind": "paragraph", "text": "Figure 1 shows the architecture.", "page": 2, "label": "¶3"},
        {"kind": "paragraph", "text": "We measured latency under load and it stayed below 200 ms.", "page": 2, "label": "¶4"},
        {"kind": "heading", "text": "References", "page": 3, "label": ""},
        {"kind": "paragraph", "text": "Smith, J. (2020). Systems.", "page": 3, "label": "¶5"},
        {"kind": "paragraph", "text": "Lee, K. (2021). Networks.", "page": 3, "label": "¶6"},
    ]
    return {"paragraphs": blocks}


def _criterion(cid: str = "crt_a", name: str = "Evaluation") -> dict:
    return {
        "id": cid,
        "name": name,
        "weight": 10,
        "description": "Measures performance and reports results",
        "aspects": [
            {"id": "measures", "label": "Measures latency", "source": "explicit"},
            {"id": "reports", "label": "Reports results", "source": "explicit"},
        ],
        "grading_mode": "analytic",
        "levels": [
            {"label": "Good", "points": 10, "description": "Measured and reported"},
            {"label": "Fair", "points": 5, "description": "Partly"},
            {"label": "Poor", "points": 0, "description": "Not done"},
        ],
    }


# ---------- the whole submission, as the model reads it ----------

def test_every_paragraph_is_included_in_order_and_never_split() -> None:
    full = full_document(_document())
    assert [p.id for p in full.passages] == ["p1", "p2", "p3", "p4", "p5", "p6"]
    assert full.passages[1].text == LONG  # 400 words: retrieval would have split it
    assert full.view.index("## 1. Introduction") < full.view.index("[p1 |") < full.view.index("## 2. Method")
    assert "[p4 | p.2 ¶4] We measured latency" in full.view


def test_offsets_match_the_highlighter() -> None:
    document = _document()
    full = full_document(document)
    quote = "it stayed below 200 ms"
    location = locate_quote(document, quote)
    passage = full.passages[3]
    assert location.start_offset == passage.start_offset + passage.text.index(quote)


def test_document_facts_are_computed_not_generated() -> None:
    facts = full_document(_document()).facts
    assert facts["pages"] == 3
    assert facts["paragraphs"] == 6
    assert [h["heading"] for h in facts["outline"]] == ["1. Introduction", "2. Method", "References"]
    assert facts["figure_and_table_captions"] == 1
    assert facts["reference_list_entries"] == 2 and facts["has_reference_list"] is True


# ---------- quotes must be the submission's own words ----------

def test_quotes_tolerate_typography_but_not_different_words() -> None:
    text = "This report defines “latency” as the delay\nseen by a user."
    assert find_quote(text, 'defines "latency" as the delay seen by a user') == "defines “latency” as the delay\nseen by a user"
    assert find_quote(text, "defines latency as the wait seen by a user") is None
    assert find_quote(text, "USER") is None  # a tiny fragment is only accepted when exact


def test_gate_keeps_verified_quotes_relocates_wrong_ids_and_drops_invented_ones() -> None:
    full = full_document(_document())
    raw = {
        "evidence": [
            # right words, wrong paragraph id
            {"passage_id": "p1", "quote": "We measured latency under load", "role": "primary",
             "relevance": "direct", "aspect_ids": ["measures"]},
            # invented
            {"passage_id": "p4", "quote": "results are reported in Table 3 with confidence intervals",
             "role": "supporting", "relevance": "direct", "aspect_ids": ["reports"]},
        ],
        # the model's own coverage claim is ignored
        "coverage": [{"aspect_id": "reports", "status": "supported"}],
    }
    gate = _normalise_gate(_criterion(), full.passages, raw, max_items=8)
    assert [(e["passage_id"], e["quote"]) for e in gate["evidence"]] == [("p4", "We measured latency under load")]
    status = {item["aspect_id"]: item["status"] for item in gate["coverage"]}
    assert status == {"measures": "supported", "reports": "missing"}
    assert gate["sufficiency"] == "partial"


# ---------- the two model steps ----------

class ScriptedLLM:
    def __init__(self, gate: dict, grade: dict | None = None) -> None:
        self.prompts: list[tuple[str, str]] = []
        self.gate, self.grade = gate, grade

    async def list_models(self):
        return []

    async def complete(self, *, purpose, prompt, metadata=None):
        self.prompts.append((purpose, prompt))
        body = self.gate if purpose == "evidence_gate" else self.grade
        return LLMResponse(json.dumps(body), "scripted", 1000, 50)


def _run_criterion(llm, criterion=None):
    settings = Settings(llm="minimax", grading_context="full")
    full = full_document(_document())
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(grading, "build_llm", lambda _settings: llm)
        return asyncio.run(grade_criterion(settings, criterion or _criterion(), full.passages, {}, full=full))


def test_evidence_step_reads_everything_and_grade_step_sees_only_verified_evidence() -> None:
    gate = {"evidence": [{"passage_id": "p4", "quote": "We measured latency under load", "role": "primary",
                          "relevance": "direct", "aspect_ids": ["measures", "reports"]}]}
    grade = {"score": 10, "level": "Good", "rationale": "Measured and reported.", "confidence": "high"}
    llm = ScriptedLLM(gate, grade)
    result = _run_criterion(llm)
    (gate_purpose, gate_prompt), (grade_purpose, grade_prompt) = llm.prompts
    assert gate_purpose == "evidence_gate" and grade_purpose == "criterion_grade"
    assert LONG in gate_prompt and "Lee, K. (2021)" in gate_prompt  # the whole submission
    assert LONG not in grade_prompt and "Lee, K. (2021)" not in grade_prompt  # only evidence
    assert "We measured latency" in grade_prompt
    assert '"reference_list_entries": 2' in grade_prompt  # facts computed by software
    assert result["score"] == 10 and result["level"] == "Good"


def test_no_verified_evidence_means_lowest_level_without_asking_for_a_mark() -> None:
    llm = ScriptedLLM({"evidence": []})
    result = _run_criterion(llm)
    assert [purpose for purpose, _ in llm.prompts] == ["evidence_gate"]
    assert (result["score"], result["level"]) == (0, "Poor")


def test_partial_coverage_caps_the_mark_whatever_the_model_says() -> None:
    gate = {"evidence": [{"passage_id": "p4", "quote": "We measured latency under load", "role": "primary",
                          "relevance": "direct", "aspect_ids": ["measures"]}]}
    llm = ScriptedLLM(gate, {"score": 10, "level": "Good", "rationale": "x", "confidence": "high"})
    result = _run_criterion(llm)
    assert (result["score"], result["level"]) == (5, "Fair")  # "reports" has no verified evidence


def test_every_criterion_shares_the_same_prompt_prefix_for_caching() -> None:
    prompts = []
    for criterion in (_criterion("crt_a", "Evaluation"), _criterion("crt_b", "Writing")):
        llm = ScriptedLLM({"evidence": []})
        _run_criterion(llm, criterion)
        prompts.append(llm.prompts[0][1])
    view = full_document(_document()).view
    shared = _FULL_GATE_HEADER + view
    assert all(prompt.startswith(shared) for prompt in prompts)
    assert prompts[0] != prompts[1]


# ---------- never truncate ----------

@pytest.fixture()
def stored(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add_all([
            User(id="usr_t", name="T", email="", role="tutor"),
            Term(id="term_t", label="T"),
            Rubric(id="rub_t", title="R", source="t", version=1, created_by="usr_t",
                   created_at=now, updated_at=now, is_sample=False, pinned=False),
            Batch(id="bat_t", name="B", term_id="term_t", status="processing", total_count=1,
                  created_by="usr_t", created_at=now, rubric_library_id="rub_t", rubric_version=1, version=1),
            Submission(id="sub_t", batch_id="bat_t", sid="SID-1", status="marking", flags_json="[]",
                       version=1, updated_at=now, document_json=json.dumps(_document())),
        ])
    return factory


def _grade(factory, settings):
    async def go():
        with factory() as session:
            return await grade_submission(session, settings, session.get(Submission, "sub_t"),
                                          session.get(Batch, "bat_t"), [_criterion()], commit_progress=True)
    return asyncio.run(go())


def test_a_submission_too_long_for_the_model_is_not_truncated(stored, monkeypatch) -> None:
    called = []
    monkeypatch.setattr(grading_service, "grade_criterion", lambda *a, **k: called.append(1))
    settings = app_settings.model_copy(update={"llm": "fake", "ai_context_tokens": 8_000})
    monkeypatch.setattr(grading_service, "_PROMPT_RESERVE_TOKENS", 7_900)  # leaves room for ~100 tokens
    with pytest.raises(DocumentTooLong, match="Mark by hand"):
        _grade(stored, settings)
    assert called == []


def test_provider_context_limit_is_routed_the_same_way(stored, monkeypatch) -> None:
    async def too_long(*_args, **_kwargs):
        raise FatalProviderError("HTTP 400: This model's maximum context length is 8192 tokens",
                                 status=400, reason="context_length")

    monkeypatch.setattr(grading_service, "grade_criterion", too_long)
    settings = app_settings.model_copy(update={"llm": "fake"})
    with pytest.raises(DocumentTooLong):
        _grade(stored, settings)


def test_worker_sends_a_too_long_submission_to_manual_marking(stored, monkeypatch) -> None:
    from app.jobs import worker

    with stored() as session:
        submission = session.get(Submission, "sub_t")
        monkeypatch.setattr(worker.BatchUseCases, "refresh_status", lambda self, batch_id: None)
        worker._route_to_manual(session, submission, "bat_t", "too_long", "Too long for the AI model. Mark by hand.")
    with stored() as session:
        submission = session.get(Submission, "sub_t")
        assert submission.status == "needs_ocr"  # the existing "mark by hand" state
        assert {"needs_manual", "too_long"} <= set(json.loads(submission.flags_json))
        assert "Mark by hand" in submission.ai_summary


def test_context_length_errors_are_recognised() -> None:
    import httpx

    from app.llm.openai_compatible import _status_error

    error = _status_error(httpx.Response(400, text='{"error":{"code":"context_length_exceeded"}}'))
    assert isinstance(error, FatalProviderError) and error.reason == "context_length"
    other = _status_error(httpx.Response(400, text='{"error":"bad request"}'))
    assert other.reason is None


def test_other_criteria_wait_for_the_first_evidence_call_then_run_together(stored, monkeypatch) -> None:
    events: list[str] = []

    async def fake(_settings, criterion, _passages, _meta, *, full=None, after_gate=None):
        events.append(f"start {criterion['id']}")
        await asyncio.sleep(0.02)
        events.append(f"gate {criterion['id']}")
        if after_gate:
            after_gate()
        await asyncio.sleep(0.02)
        return {"score": 5, "level": "", "rationale": "r", "confidence": "low", "evidence": [], "coverage": []}

    monkeypatch.setattr(grading_service, "grade_criterion", fake)
    settings = app_settings.model_copy(update={"llm": "fake", "criterion_concurrency": 3})
    criteria = [_criterion(f"crt_{i}") for i in range(3)]

    async def go():
        with stored() as session:
            return await grade_submission(session, settings, session.get(Submission, "sub_t"),
                                          session.get(Batch, "bat_t"), criteria, commit_progress=True)

    asyncio.run(go())
    assert events[:2] == ["start crt_0", "gate crt_0"]  # the first one primes the provider cache
    assert events[2:4] == ["start crt_1", "start crt_2"]  # then the rest go together


def test_the_rationale_cites_pages_and_paragraphs_not_internal_ids() -> None:
    gate = {"evidence": [{"passage_id": "p4", "quote": "We measured latency under load", "role": "primary",
                          "relevance": "direct", "aspect_ids": ["measures", "reports"]}]}
    grade = {"score": 10, "level": "Good", "rationale": "Latency is measured (p4, p1); see p99.", "confidence": "high"}
    llm = ScriptedLLM(gate, grade)
    result = _run_criterion(llm)
    assert result["rationale"] == "Latency is measured (p.2 ¶4, p.1 ¶1); see p99."
    assert "never by passage id" in llm.prompts[1][1]
