"""Provider rate limits, one retry layer per failure kind, criterion concurrency, lost leases."""

import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.db.base import Base
from app.db.models.batch import Batch
from app.db.models.core import Term, User
from app.db.models.job import Job
from app.db.models.rubric import Rubric
from app.db.models.submission import AIResult, Submission
from app.jobs import worker as worker_module
from app.llm.openai_compatible import OpenAICompatibleLLM, retry_after_seconds
from app.llm.protocol import FatalProviderError, RetryableProviderError
from app.llm.ratelimit import ProviderGate
from app.services import grading_service
from app.services.grading_service import CriterionFailed, LeaseLost, grade_submission

OK_BODY = {"model": "m", "choices": [{"message": {"content": '{"ok": true}'}}], "usage": {}}


# ---------- Retry-After ----------

def test_retry_after_reads_seconds_dates_and_milliseconds() -> None:
    now = datetime(2026, 10, 27, 5, 0, 0, tzinfo=timezone.utc)
    assert retry_after_seconds({"Retry-After": "7"}) == 7
    assert retry_after_seconds({"retry-after-ms": "1500"}) == 1.5
    assert retry_after_seconds({"Retry-After": "Tue, 27 Oct 2026 05:00:30 GMT"}, now=now) == 30
    assert retry_after_seconds({"Retry-After": "soon"}) is None
    assert retry_after_seconds({}) is None


# ---------- LLM client ----------

def _client(handler, **kwargs) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        "https://provider.test/v1", "key", "m", transport=httpx.MockTransport(handler),
        gate=ProviderGate(4), max_backoff_seconds=1, **kwargs,
    )


def test_429_waits_for_retry_after_and_pauses_every_slot() -> None:
    calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(time.monotonic())
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.3"}, text="slow down")
        return httpx.Response(200, json=OK_BODY)

    llm = _client(handler)
    response = asyncio.run(llm.complete(purpose="criterion_grade", prompt="x"))
    assert response.text == '{"ok": true}'
    assert llm.retries == 1
    assert calls[1] - calls[0] >= 0.29  # waited what the provider asked for


def test_shared_cool_down_holds_other_calls_back() -> None:
    gate = ProviderGate(4)
    gate.cool_down(0.3)

    async def go() -> float:
        started = time.monotonic()
        async with gate.slot():
            return time.monotonic() - started

    assert asyncio.run(go()) >= 0.25


def test_wrong_key_or_model_fails_at_once_without_retries() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, text="invalid api key")

    llm = _client(handler)
    with pytest.raises(FatalProviderError, match="HTTP 401"):
        asyncio.run(llm.complete(purpose="criterion_grade", prompt="x"))
    assert len(calls) == 1


def test_overload_gives_up_after_the_configured_retries() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, headers={"Retry-After": "0"}, text="overloaded")

    llm = _client(handler, max_retries=2)
    with pytest.raises(RetryableProviderError, match="gave up after 3 attempts"):
        asyncio.run(llm.complete(purpose="criterion_grade", prompt="x"))
    assert len(calls) == 3


def test_timeouts_are_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json=OK_BODY)

    assert asyncio.run(_client(handler).complete(purpose="criterion_grade", prompt="x")).text
    assert len(calls) == 2


def test_gate_caps_calls_in_flight_across_threads() -> None:
    gate = ProviderGate(2)
    peak = [0]
    lock = threading.Lock()

    async def one() -> None:
        async with gate.slot():
            with lock:
                peak[0] = max(peak[0], gate.in_flight)
            await asyncio.sleep(0.05)

    threads = [threading.Thread(target=lambda: asyncio.run(one())) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak[0] == 2


# ---------- grading: one retry layer, concurrency, lease ----------

@pytest.fixture()
def graded(monkeypatch):
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
                       version=1, updated_at=now,
                       document_json=json.dumps({"paragraphs": [{"text": "Some text.", "page": 1}]})),
        ])
    monkeypatch.setattr(grading_service, "retrieve_passages", lambda *a, **k: [])
    settings = app_settings.model_copy(deep=True)
    settings.llm = "fake"
    settings.criterion_concurrency = 3
    criteria = [{"id": f"crt_{i}", "name": f"C{i}", "weight": 10, "levels": []} for i in range(4)]
    return factory, settings, criteria


def _run(factory, settings, criteria, **kwargs):
    async def go():
        with factory() as session:
            submission = session.get(Submission, "sub_t")
            batch = session.get(Batch, "bat_t")
            return await grade_submission(session, settings, submission, batch, criteria,
                                          commit_progress=True, **kwargs)
    return asyncio.run(go())


def _result(score: float = 7) -> dict:
    return {"score": score, "level": "", "rationale": "r", "confidence": "medium", "evidence": [], "coverage": []}


def test_criteria_of_one_submission_are_graded_concurrently(graded, monkeypatch) -> None:
    factory, settings, criteria = graded
    active, peak = [0], [0]

    async def fake_grade(_settings, criterion, _passages, _meta):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        await asyncio.sleep(0.05)
        active[0] -= 1
        return _result()

    monkeypatch.setattr(grading_service, "grade_criterion", fake_grade)
    summary = _run(factory, settings, criteria)
    assert peak[0] == 3  # criterion_concurrency
    assert summary["ai_total"] == 28
    with factory() as session:
        assert len(list(session.scalars(select(AIResult)))) == 4


def test_provider_failure_is_not_retried_again_and_other_criteria_are_kept(graded, monkeypatch) -> None:
    factory, settings, criteria = graded
    calls: dict[str, int] = {}

    async def fake_grade(_settings, criterion, _passages, _meta):
        calls[criterion["id"]] = calls.get(criterion["id"], 0) + 1
        if criterion["id"] == "crt_2":
            raise FatalProviderError("HTTP 401: invalid api key")
        return _result()

    monkeypatch.setattr(grading_service, "grade_criterion", fake_grade)
    with pytest.raises(CriterionFailed, match="HTTP 401") as raised:
        _run(factory, settings, criteria)
    assert raised.value.final is True
    assert calls["crt_2"] == 1
    with factory() as session:  # the three good criteria are saved; a retry resumes from them
        assert {r.criterion_id for r in session.scalars(select(AIResult))} == {"crt_0", "crt_1", "crt_3"}


def test_invalid_model_output_is_retried_once(graded, monkeypatch) -> None:
    factory, settings, criteria = graded
    calls = [0]

    async def fake_grade(_settings, criterion, _passages, _meta):
        calls[0] += 1
        raise ValueError("The grading model did not return a JSON object")

    monkeypatch.setattr(grading_service, "grade_criterion", fake_grade)
    with pytest.raises(CriterionFailed, match="rejected after 2 attempts"):
        _run(factory, settings, criteria[:1])
    assert calls[0] == 2


def test_lost_lease_stops_grading_before_anything_is_written(graded, monkeypatch) -> None:
    factory, settings, criteria = graded

    async def fake_grade(*_args):
        return _result()

    monkeypatch.setattr(grading_service, "grade_criterion", fake_grade)
    with pytest.raises(LeaseLost):
        _run(factory, settings, criteria, still_owned=lambda: False)
    with factory() as session:
        assert list(session.scalars(select(AIResult))) == []


def test_ai_results_are_unique_per_submission_criterion(graded) -> None:
    factory, _settings, _criteria = graded
    now = datetime.now(timezone.utc)
    row = dict(submission_id="sub_t", criterion_id="crt_0", level="", score=1, rationale="", confidence="low",
               provider="fake", model="m", prompt_version="v", created_at=now)
    with factory() as session:
        session.add(AIResult(id="air_1", **row))
        session.commit()
        session.add(AIResult(id="air_2", **row))
        with pytest.raises(IntegrityError):
            session.commit()
    names = {index["name"] for index in inspect(factory.kw["bind"]).get_indexes("ai_results")}
    assert "uq_ai_results_submission_criterion" in names


# ---------- job queue: final errors are not run again ----------

def _queued_job(factory) -> None:
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    with factory.begin() as session:
        session.add(Job(id="job_t", kind="grade", submission_id="sub_t", batch_id="bat_t",
                        payload_json=json.dumps({"submission_id": "sub_t", "batch_id": "bat_t"}),
                        status="queued", attempts=0, run_after=now, created_at=now, updated_at=now))


def test_final_error_fails_the_job_on_the_first_attempt(graded, monkeypatch) -> None:
    factory, _settings, _criteria = graded
    _queued_job(factory)

    def boom(_kind, _payload):
        raise CriterionFailed("C1 Argument: HTTP 401: invalid api key", final=True)

    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module, "handle", boom)
    monkeypatch.setattr(worker_module.BatchUseCases, "refresh_status", lambda self, batch_id: None)
    assert worker_module.run_once("w:1") is True
    with factory() as session:
        job = session.get(Job, "job_t")
        assert (job.status, job.attempts) == ("failed", 1)
        submission = session.get(Submission, "sub_t")
        assert submission.status == "failed" and "HTTP 401" in submission.error_reason


def test_unexpected_crash_is_still_requeued(graded, monkeypatch) -> None:
    factory, _settings, _criteria = graded
    _queued_job(factory)

    def crash(_kind, _payload):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(worker_module, "SessionLocal", factory)
    monkeypatch.setattr(worker_module, "handle", crash)
    worker_module.run_once("w:1")
    with factory() as session:
        assert session.get(Job, "job_t").status == "queued"


def test_slot_gives_up_its_job_when_the_lease_cannot_be_renewed(monkeypatch) -> None:
    class Locked:
        def begin(self):
            raise RuntimeError("database is locked")

    monkeypatch.setattr(worker_module, "SessionLocal", Locked())
    monkeypatch.setattr(worker_module.settings, "job_lease_seconds", 3)  # renew every 1 s
    lease = worker_module._Lease()
    stop = threading.Event()
    thread = threading.Thread(target=worker_module._renew_lease, args=("job_x", "w:1", stop, lease))
    thread.start()
    thread.join(timeout=5)
    stop.set()
    assert lease.owned() is False  # stopped before the 3 s lease could expire
