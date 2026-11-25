"""Pause holds a batch's work back and resume continues it; terminate stays final."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.submissions import retry_submission
from app.config import settings as app_settings
from app.db.base import Base
from app.db.models.batch import Batch
from app.db.models.core import Term, User
from app.db.models.job import Job
from app.db.models.rubric import Rubric
from app.db.models.submission import AIResult, Submission
from app.jobs import worker as worker_module
from app.jobs.queue import JobQueue
from app.services import grading_service
from app.services.batch_service import BatchUseCases
from app.services.grading_service import BatchPaused, grade_submission

DOCUMENT = {"paragraphs": [{"kind": "paragraph", "text": "Some submission text to grade.", "page": 1, "label": "¶1"}]}


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pause.sqlite3'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add_all([
            User(id="usr_t", name="T", email="", role="tutor"),
            Term(id="term_t", label="T"),
            Rubric(id="rub_t", title="R", source="t", version=1, created_by="usr_t",
                   created_at=now, updated_at=now, is_sample=False, pinned=False),
            Batch(id="bat_t", name="Big batch", term_id="term_t", status="processing", total_count=4,
                  created_by="usr_t", created_at=now, rubric_library_id="rub_t", rubric_version=1, version=1),
        ])
        for i in range(4):
            session.add(Submission(id=f"sub_{i}", batch_id="bat_t", sid=f"SID-{i}", status="queued",
                                   flags_json="[]", version=1, updated_at=now,
                                   document_json=json.dumps(DOCUMENT)))
            session.add(Job(id=f"job_{i}", kind="grade", submission_id=f"sub_{i}", batch_id="bat_t",
                            payload_json=json.dumps({"submission_id": f"sub_{i}", "batch_id": "bat_t"}),
                            status="running" if i == 0 else "queued", attempts=1 if i == 0 else 0,
                            lease_owner="w:1" if i == 0 else None,
                            lease_until=now + timedelta(seconds=60) if i == 0 else None,
                            run_after=now - timedelta(seconds=1), created_at=now + timedelta(seconds=i),
                            updated_at=now))
    return factory


def _jobs(factory) -> dict[str, str]:
    with factory() as session:
        return {job.id: job.status for job in session.scalars(select(Job))}


def _batch(factory) -> Batch:
    with factory() as session:
        return session.get(Batch, "bat_t")


def test_pause_holds_queued_work_and_the_queue_skips_it(db) -> None:
    with db.begin() as session:
        result = BatchUseCases(session).pause("bat_t", "usr_t", 1)
    assert (result["status"], result["held"], result["finishing"]) == ("paused", 3, 1)
    assert _jobs(db) == {"job_0": "running", "job_1": "paused", "job_2": "paused", "job_3": "paused"}
    with db.begin() as session:
        assert JobQueue(session).lease("w:2", 60) is None  # nothing for another slot to pick up
        BatchUseCases(session).refresh_status("bat_t")  # work still held → stays paused
    assert _batch(db).status == "paused"


def test_resume_puts_the_work_back_in_the_queue(db) -> None:
    with db.begin() as session:
        BatchUseCases(session).pause("bat_t", "usr_t", 1)
    with db.begin() as session:
        result = BatchUseCases(session).resume("bat_t", "usr_t", 2)
    assert (result["status"], result["released"]) == ("processing", 3)
    assert _jobs(db) == {"job_0": "running", "job_1": "queued", "job_2": "queued", "job_3": "queued"}
    with db.begin() as session:
        assert JobQueue(session).lease("w:2", 60).id == "job_1"


def test_only_a_running_batch_can_pause_and_only_a_paused_one_resume(db) -> None:
    with db.begin() as session, pytest.raises(RuntimeError, match="invalid_transition"):
        BatchUseCases(session).resume("bat_t", "usr_t", 1)
    with db.begin() as session:
        BatchUseCases(session).pause("bat_t", "usr_t", 1)
    with db.begin() as session, pytest.raises(RuntimeError, match="invalid_transition"):
        BatchUseCases(session).pause("bat_t", "usr_t", 2)
    with db.begin() as session, pytest.raises(RuntimeError, match="version_conflict"):
        BatchUseCases(session).resume("bat_t", "usr_t", 1)


def test_terminating_a_paused_batch_cancels_the_held_work(db) -> None:
    with db.begin() as session:
        BatchUseCases(session).pause("bat_t", "usr_t", 1)
    with db.begin() as session:
        BatchUseCases(session).cancel("bat_t", "usr_t", "stop", 2)
    assert set(_jobs(db).values()) == {"running", "cancelled"}
    assert _batch(db).status == "cancelled"


def test_criteria_already_sent_are_kept_and_the_rest_wait(db, monkeypatch) -> None:
    sent: list[str] = []

    async def fake_grade(_settings, criterion, _passages, _meta, *, full=None, after_gate=None):
        sent.append(criterion["id"])
        if len(sent) == 1:  # the tutor presses Pause while the first criterion is with the AI
            with db.begin() as other:
                BatchUseCases(other).pause("bat_t", "usr_t", 1)
        return {"score": 4, "level": "", "rationale": "r", "confidence": "low", "evidence": [], "coverage": []}

    monkeypatch.setattr(grading_service, "grade_criterion", fake_grade)
    settings = app_settings.model_copy(update={"llm": "fake", "criterion_concurrency": 1})
    criteria = [{"id": f"crt_{i}", "name": f"C{i}", "weight": 5, "levels": []} for i in range(3)]

    async def go():
        with db() as session:
            await grade_submission(session, settings, session.get(Submission, "sub_0"),
                                   session.get(Batch, "bat_t"), criteria, commit_progress=True)

    with pytest.raises(BatchPaused):
        asyncio.run(go())
    assert sent == ["crt_0"]  # nothing new was sent after the pause
    with db() as session:  # the criterion already with the AI was saved
        assert [r.criterion_id for r in session.scalars(select(AIResult))] == ["crt_0"]


def test_a_paused_job_is_set_aside_without_using_up_an_attempt(db, monkeypatch) -> None:
    def paused_handle(_kind, _payload):
        raise BatchPaused("batch_paused")

    with db.begin() as session:
        session.get(Job, "job_0").status = "done"
    monkeypatch.setattr(worker_module, "SessionLocal", db)
    monkeypatch.setattr(worker_module, "handle", paused_handle)
    assert worker_module.run_once("w:1") is True
    with db() as session:
        job = session.get(Job, "job_1")
        assert (job.status, job.attempts, job.lease_owner) == ("paused", 0, None)


def _retry(db, submission_id: str):
    with db.begin() as session:
        version = session.get(Submission, submission_id).version
    with db() as session:
        return retry_submission(submission_id, {"version": version}, session,
                                app_settings.model_copy(update={"llm": "fake"}))


def test_retrying_one_submission_does_not_revive_a_terminated_batch(db) -> None:
    with db.begin() as session:
        session.get(Submission, "sub_3").status = "failed"
        BatchUseCases(session).cancel("bat_t", "usr_t", "stop", 1)
    with pytest.raises(HTTPException) as raised:
        _retry(db, "sub_3")
    assert raised.value.status_code == 409
    assert _batch(db).status == "cancelled"


def test_retrying_in_a_paused_batch_waits_for_resume(db) -> None:
    with db.begin() as session:
        session.get(Submission, "sub_3").status = "failed"
        BatchUseCases(session).pause("bat_t", "usr_t", 1)
    result = _retry(db, "sub_3")
    with db() as session:
        assert session.get(Job, result["job_id"]).status == "paused"
        assert session.get(Batch, "bat_t").status == "paused"


def test_worker_puts_a_paused_submission_back_in_the_queue(db, monkeypatch) -> None:
    async def paused_midway(*_args, **_kwargs):
        raise BatchPaused("batch_paused")

    monkeypatch.setattr(worker_module, "SessionLocal", db)
    monkeypatch.setattr(worker_module, "grade_submission", paused_midway)
    payload = {"submission_id": "sub_1", "batch_id": "bat_t", "rubric_id": "rub_t", "rubric_version": 1}
    with pytest.raises(BatchPaused):
        asyncio.run(worker_module.handle_grade(payload))
    with db() as session:
        submission = session.get(Submission, "sub_1")
        assert submission.status == "queued"
        assert submission.ai_summary.startswith("Paused · 0/")


def test_a_paused_batch_must_be_terminated_before_it_can_be_deleted(db) -> None:
    with db.begin() as session:
        BatchUseCases(session).pause("bat_t", "usr_t", 1)
    with db.begin() as session, pytest.raises(RuntimeError, match="batch_must_be_cancelled"):
        BatchUseCases(session).delete("bat_t", "usr_t", 2)
