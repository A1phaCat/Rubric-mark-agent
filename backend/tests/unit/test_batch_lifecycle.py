from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.audit import AuditLog
from app.db.models.batch import Batch
from app.db.models.job import Job
from app.db.models.review import Review
from app.db.models.submission import AIResult, Evidence, File, Submission
from app.services.batch_service import BatchUseCases


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _batch(session: Session, status: str = "processing") -> Batch:
    now = datetime.now(timezone.utc)
    batch = Batch(
        id="bat_test",
        name="Lifecycle test",
        term_id="term_test",
        status=status,
        total_count=1,
        created_by="usr_test",
        created_at=now,
        version=1,
    )
    session.add(batch)
    session.add(
        Submission(
            id="sub_test",
            batch_id=batch.id,
            sid="SID-1",
            status="queued",
            flags_json="[]",
            is_mock=False,
            version=1,
            updated_at=now,
        )
    )
    session.add(
        Job(
            id="job_test",
            kind="grade",
            submission_id="sub_test",
            batch_id=batch.id,
            payload_json="{}",
            status="queued",
            attempts=0,
            run_after=now,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    return batch


def test_cancel_batch_stops_queued_work_and_marks_submission() -> None:
    session = _session()
    batch = _batch(session)

    result = BatchUseCases(session).cancel(batch.id, "usr_test", "No longer needed", 1)
    session.flush()

    assert result["status"] == "cancelled"
    assert session.get(Batch, batch.id).status == "cancelled"
    assert session.get(Submission, "sub_test").status == "cancelled"
    assert session.get(Job, "job_test").status == "cancelled"
    assert session.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_delete_batch_removes_dependent_records_and_returns_file_paths() -> None:
    session = _session()
    batch = _batch(session, status="cancelled")
    now = datetime.now(timezone.utc)
    stored_file = File(
        id="fil_test",
        batch_id=batch.id,
        original_name="SID-1.txt",
        path="C:/safe/example.txt",
        sha256="0" * 64,
        size=1,
        mime="text/plain",
        created_at=now,
    )
    session.add(stored_file)
    submission = session.get(Submission, "sub_test")
    submission.file_id = stored_file.id
    result_row = AIResult(
        id="air_test",
        submission_id=submission.id,
        criterion_id="crt_test",
        level="Level",
        score=1,
        rationale="Rationale",
        minor_json="[]",
        coverage_json="[]",
        sufficiency="partial",
        confidence="low",
        provider="fake",
        model="fake",
        prompt_version="test",
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        created_at=now,
    )
    session.add(result_row)
    session.add(
        Evidence(
            id="evd_test",
            ai_result_id=result_row.id,
            role="supporting",
            quote="text",
            page=1,
            para="p1",
            char_start=0,
            char_end=4,
            document_version=1,
            valid=True,
        )
    )
    session.add(
        Review(
            id="rev_test",
            submission_id=submission.id,
            criterion_id="crt_test",
            score=1,
            comment="",
            status="ai_suggested",
            updated_by="usr_test",
            updated_at=now,
            version=1,
        )
    )
    session.flush()

    result = BatchUseCases(session).delete(batch.id, "usr_test", 1)
    session.flush()

    assert result["deleted"] is True
    assert result["file_paths"] == ["C:/safe/example.txt"]
    assert session.get(Batch, batch.id) is None
    assert session.get(Submission, submission.id) is None
    assert session.get(File, stored_file.id) is None
    assert session.get(AIResult, result_row.id) is None
    assert session.get(Evidence, "evd_test") is None
    assert session.get(Review, "rev_test") is None
    assert session.get(Job, "job_test") is None

