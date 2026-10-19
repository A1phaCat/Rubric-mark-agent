from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.settings import load_ai_settings
from app.config import settings
from app.db.models.batch import Batch
from app.db.models.job import Job
from app.db.models.rubric import RubricCriterion
from app.db.models.submission import File, Submission
from app.db.session import SessionLocal
from app.domain.states import BatchStatus, SubmissionStatus
from app.events.bus import event_bus
from app.extract.service import extract_document
from app.jobs.queue import JobQueue
from app.services.grading_service import BatchCancelled, grade_submission


def handle(kind: str, payload: dict[str, object]) -> None:
    if kind == "demo_progress":
        batch_id = str(payload["batch_id"])
        event_bus.publish(batch_id, {"event": "batch_progress", "data": payload})
        return
    if kind == "grade":
        asyncio.run(handle_grade(payload))
        return
    raise ValueError(f"Unsupported job kind: {kind}")


async def handle_grade(payload: dict[str, object]) -> None:
    submission_id = str(payload["submission_id"])
    batch_id = str(payload["batch_id"])
    session = SessionLocal()
    try:
        runtime_settings = settings.model_copy(deep=True)
        load_ai_settings(session, runtime_settings)
        submission = session.get(Submission, submission_id)
        batch = session.get(Batch, batch_id)
        if submission is None or batch is None:
            raise KeyError(submission_id)
        if batch.status == BatchStatus.CANCELLED.value:
            return
        criteria = list(
            session.scalars(
                select(RubricCriterion)
                .where(
                    RubricCriterion.rubric_id == str(payload["rubric_id"]),
                    RubricCriterion.rubric_version == int(payload["rubric_version"]),
                )
                .order_by(RubricCriterion.position)
            )
        )
        criterion_payloads: list[dict[str, Any]] = [
            {
                "id": criterion.id,
                "name": criterion.name,
                "weight": criterion.weight,
                "levels": json.loads(criterion.levels_json or "[]"),
                "grading_mode": criterion.grading_mode,
                "aspects": json.loads(criterion.aspects_json or "[]"),
            }
            for criterion in criteria
        ]
        if not submission.document_json:
            stored_file = session.get(File, submission.file_id) if submission.file_id else None
            if stored_file is None:
                raise ValueError("submission_file_missing")
            document = extract_document(Path(stored_file.path), submission.id, stored_file.mime)
            submission.document_json = json.dumps(document, ensure_ascii=False)
            submission.word_count = int(document["word_count"])
            submission.text_quality = "text_layer"
            submission.document_version = int(document["version"])
            stored_file.pages = int(document["page_count"])
            stored_file.text_layer = True
            submission.is_mock = False
        submission.status = SubmissionStatus.MARKING.value
        submission.ai_summary = f"0/{len(criteria)} criteria processed"
        submission.error_reason = None
        submission.version += 1
        session.commit()

        runtime_settings.llm = batch.model_provider or runtime_settings.llm
        runtime_settings.ai_model = batch.model_name or runtime_settings.ai_model
        try:
            await grade_submission(
                session,
                runtime_settings,
                submission,
                batch,
                criterion_payloads,
                force=bool(payload.get("force", False)),
                commit_progress=True,
            )
        except BatchCancelled:
            session.rollback()
            return
        submission.status = SubmissionStatus.AI_DONE.value
        submission.ai_summary = (
            f"{len(criteria)}/{len(criteria)} criteria processed · {submission.ai_summary}"
        )
        submission.version += 1
        _update_batch_state(session, batch_id)
        session.commit()
        event_bus.publish(
            batch_id,
            {
                "event": "batch_progress",
                "data": {"batch_id": batch_id, "submission_id": submission_id},
            },
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _update_batch_state(session: Session, batch_id: str) -> None:
    batch = session.get(Batch, batch_id)
    if batch is None or batch.status == BatchStatus.CANCELLED.value:
        return
    rows = dict(
        session.execute(
            select(Submission.status, func.count())
            .where(Submission.batch_id == batch_id)
            .group_by(Submission.status)
        ).all()
    )
    processing = sum(
        rows.get(state, 0)
        for state in ("uploaded", "extracting", "ocr_running", "queued", "marking")
    )
    if processing:
        batch.status = BatchStatus.PROCESSING.value
    elif rows.get(SubmissionStatus.FAILED.value, 0) == batch.total_count:
        batch.status = BatchStatus.FAILED_ALL.value
    else:
        batch.status = BatchStatus.IN_REVIEW.value
    batch.version += 1


def _mark_terminal_failure(payload: dict[str, object], error: str) -> None:
    submission_id = str(payload.get("submission_id") or "")
    batch_id = str(payload.get("batch_id") or "")
    if not submission_id:
        return
    with SessionLocal.begin() as session:
        submission = session.get(Submission, submission_id)
        if submission is not None:
            submission.status = SubmissionStatus.FAILED.value
            submission.error_reason = error[:1000]
            submission.ai_summary = "AI grading failed after automatic retries"
            submission.version += 1
        if batch_id:
            _update_batch_state(session, batch_id)


def run_once() -> bool:
    leased: tuple[str, str, dict[str, object], int] | None = None
    with SessionLocal.begin() as session:
        queue = JobQueue(session)
        job = queue.lease(settings.worker_id, settings.job_lease_seconds)
        if job is None:
            return False
        leased = (job.id, job.kind, json.loads(job.payload_json), job.attempts)
    job_id, kind, payload, attempts = leased
    error: str | None = None
    try:
        handle(kind, payload)
    except Exception as exc:  # worker boundary must persist all failures
        error = str(exc).strip() or type(exc).__name__
    with SessionLocal.begin() as session:
        job = session.get(Job, job_id)
        if job is None:
            return True
        queue = JobQueue(session)
        if error is None:
            queue.done(job, settings.worker_id)
        else:
            queue.fail(job, settings.worker_id, error, settings.job_max_attempts)
    if error is not None and attempts >= settings.job_max_attempts:
        _mark_terminal_failure(payload, error)
    return True


def write_heartbeat() -> None:
    target = settings.runtime_paths()["cache"] / "worker-heartbeat.json"
    target.write_text(
        json.dumps(
            {"worker_id": settings.worker_id, "last_seen": datetime.now(timezone.utc).isoformat()}
        ),
        encoding="utf-8",
    )


def main() -> None:
    print(f"worker {settings.worker_id} started", flush=True)
    while True:
        write_heartbeat()
        if not run_once():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
