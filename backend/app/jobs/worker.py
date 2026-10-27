from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.config import settings
from app.db.models.batch import Batch
from app.db.models.job import Job
from app.db.models.rubric import RubricCriterion
from app.db.models.submission import AIResult, File, Submission
from app.db.session import SessionLocal
from app.domain.states import BatchStatus, SubmissionStatus
from app.jobs.queue import JobQueue
from app.services.batch_service import BatchUseCases
from app.services.grading_service import (
    BatchCancelled,
    BatchPaused,
    DocumentTooLong,
    LeaseLost,
    grade_submission,
)
from app.services.settings_service import load_ai_settings
from app.services.submission_service import apply_extraction


class _Lease:
    """Whether this slot still owns its job, as seen by the lease-renewal thread."""

    def __init__(self) -> None:
        self.lost = threading.Event()
        self.renewed_at = time.monotonic()

    def owned(self) -> bool:
        return not self.lost.is_set()


# The lease of the job this slot thread is running (each slot is one thread, and the
# grading coroutine runs on that thread's own event loop).
_CURRENT = threading.local()


def handle(kind: str, payload: dict[str, object]) -> None:
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
        if batch.status == BatchStatus.PAUSED.value:
            raise BatchPaused("batch_paused")  # the slot sets this job aside until resume
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
                "description": criterion.description or "",
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
            apply_extraction(session, submission, stored_file)
            if submission.status == SubmissionStatus.NEEDS_OCR.value:
                # Nothing to grade without a text layer; route to manual marking.
                BatchUseCases(session).refresh_status(batch_id)
                session.commit()
                return
        force = bool(payload.get("force", False))
        completed_criteria = 0
        if not force:
            completed_criteria = (
                session.scalar(
                    select(func.count(func.distinct(AIResult.criterion_id))).where(
                        AIResult.submission_id == submission.id
                    )
                )
                or 0
            )
        submission.status = SubmissionStatus.MARKING.value
        submission.ai_summary = (
            f"{min(int(completed_criteria), len(criteria))}/{len(criteria)} criteria processed"
        )
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
                force=force,
                commit_progress=True,
                still_owned=getattr(_CURRENT, "owned", None),
            )
        except (BatchCancelled, LeaseLost):
            # Cancelled: nothing more to do. Lease lost: the slot that now owns the job
            # carries on from the criteria already committed.
            session.rollback()
            return
        except BatchPaused:
            # Criteria finished before the pause are committed; the rest wait for resume.
            session.rollback()
            done = int(
                session.scalar(
                    select(func.count(func.distinct(AIResult.criterion_id))).where(
                        AIResult.submission_id == submission.id
                    )
                )
                or 0
            )
            submission.status = SubmissionStatus.QUEUED.value
            submission.ai_summary = f"Paused · {done}/{len(criteria)} criteria done"
            submission.version += 1
            session.commit()
            raise
        except DocumentTooLong as exc:
            # Never truncate: a submission the model cannot read whole is marked by a tutor.
            session.rollback()
            _route_to_manual(session, submission, batch_id, "too_long", str(exc))
            return
        submission.status = SubmissionStatus.AI_DONE.value
        submission.ai_summary = (
            f"{len(criteria)}/{len(criteria)} criteria processed · {submission.ai_summary}"
        )
        submission.version += 1
        # Make the terminal submission state visible to the aggregate query.
        # This is especially important after grade_submission committed
        # criterion-level progress during a long external-provider run.
        session.flush()
        BatchUseCases(session).refresh_status(batch_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _route_to_manual(
    session: Any, submission: Submission, batch_id: str, reason: str, message: str
) -> None:
    flags = set(json.loads(submission.flags_json or "[]")) | {"needs_manual", reason}
    submission.flags_json = json.dumps(sorted(flags))
    # needs_ocr is the existing "mark by hand" state; the flag says why.
    submission.status = SubmissionStatus.NEEDS_OCR.value
    submission.ai_summary = message
    submission.error_reason = None
    submission.version += 1
    session.flush()
    BatchUseCases(session).refresh_status(batch_id)
    session.commit()


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
            BatchUseCases(session).refresh_status(batch_id)


def _renew_lease(
    job_id: str, owner: str, stop: threading.Event, lease: _Lease | None = None
) -> None:
    lease = lease or _Lease()
    interval = max(1.0, settings.job_lease_seconds / 3)
    while not stop.wait(interval):
        try:
            with SessionLocal.begin() as session:
                job = session.get(Job, job_id)
                if job is None or job.status != "running" or job.lease_owner != owner:
                    lease.lost.set()
                    print(f"worker {owner} no longer owns {job_id}; stopping it", flush=True)
                    return
                JobQueue(session).heartbeat(job, owner, settings.job_lease_seconds)
            lease.renewed_at = time.monotonic()
        except Exception as exc:  # keep the grading call alive through transient SQLite locks
            print(f"worker {owner} could not renew {job_id}: {exc}", flush=True)
            # Stop before the lease can expire: after that another slot may take the job
            # and both would write the same criteria.
            if time.monotonic() - lease.renewed_at > settings.job_lease_seconds * 0.75:
                lease.lost.set()
                print(f"worker {owner} gave up {job_id}: lease could not be renewed", flush=True)
                return


def run_once(owner: str | None = None) -> bool:
    owner = owner or settings.worker_id
    leased: tuple[str, str, dict[str, object], int] | None = None
    with SessionLocal.begin() as session:
        queue = JobQueue(session)
        job = queue.lease(owner, settings.job_lease_seconds)
        if job is None:
            return False
        leased = (job.id, job.kind, json.loads(job.payload_json), job.attempts)
    job_id, kind, payload, attempts = leased
    error: str | None = None
    final = False
    lease = _Lease()
    lease_stop = threading.Event()
    lease_thread = threading.Thread(
        target=_renew_lease,
        args=(job_id, owner, lease_stop, lease),
        name=f"lease-{owner}",
        daemon=True,
    )
    lease_thread.start()
    _CURRENT.owned = lease.owned
    parked = False
    try:
        handle(kind, payload)
    except BatchPaused:
        parked = True
    except Exception as exc:  # worker boundary must persist all failures
        error = str(exc).strip() or type(exc).__name__
        # Provider and model-output failures were already retried where they happened.
        final = bool(getattr(exc, "final", False))
    finally:
        _CURRENT.owned = None
        lease_stop.set()
        lease_thread.join(timeout=1)
    with SessionLocal.begin() as session:
        job = session.get(Job, job_id)
        if job is None:
            return True
        if job.status != "running" or job.lease_owner != owner:
            return True
        queue = JobQueue(session)
        if parked:
            queue.park(job, owner)
        elif error is None:
            queue.done(job, owner)
        else:
            queue.fail(job, owner, error, 1 if final else settings.job_max_attempts)
    if error is not None and (final or attempts >= settings.job_max_attempts):
        _mark_terminal_failure(payload, error)
    return True


def write_heartbeat() -> None:
    target = settings.runtime_paths()["cache"] / "worker-heartbeat.json"
    target.write_text(
        json.dumps(
            {
                "worker_id": settings.worker_id,
                "concurrency": settings.worker_concurrency,
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def _slot_loop(slot: int, stop: threading.Event) -> None:
    owner = f"{settings.worker_id}:{slot + 1}"
    while not stop.is_set():
        try:
            worked = run_once(owner)
        except Exception as exc:  # isolate one slot from queue/database failures
            print(f"worker {owner} error: {exc}", flush=True)
            stop.wait(1)
            continue
        if not worked:
            stop.wait(0.5)


def main() -> None:
    concurrency = settings.worker_concurrency
    stop = threading.Event()
    print(f"worker {settings.worker_id} started with {concurrency} slots", flush=True)
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="marker-worker") as pool:
        futures = [pool.submit(_slot_loop, slot, stop) for slot in range(concurrency)]
        try:
            while not stop.wait(1):
                write_heartbeat()
        except KeyboardInterrupt:
            stop.set()
        finally:
            stop.set()
            for future in futures:
                future.result()


if __name__ == "__main__":
    main()
