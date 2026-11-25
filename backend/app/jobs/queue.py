from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db.models.job import Job
from app.domain.ids import new_id


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobQueue:
    """Owns job writes: enqueue, lease, heartbeat, completion and failure."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self, kind: str, payload: dict[str, Any], *, run_after: datetime | None = None
    ) -> Job:
        now = utcnow()
        job = Job(
            id=new_id("job"),
            kind=kind,
            submission_id=payload.get("submission_id"),
            batch_id=payload.get("batch_id"),
            payload_json=json.dumps(payload),
            status="queued",
            attempts=0,
            run_after=run_after or now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def lease(self, owner: str, lease_seconds: int) -> Job | None:
        now = utcnow()
        candidate_id = (
            select(Job)
            .where(
                Job.run_after <= now,
                or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now)),
            )
            .order_by(Job.created_at)
            .limit(1)
            .with_only_columns(Job.id)
            .scalar_subquery()
        )
        job_id = self.session.scalar(
            update(Job)
            .where(Job.id == candidate_id)
            .values(
                status="running",
                lease_owner=owner,
                lease_until=now + timedelta(seconds=lease_seconds),
                heartbeat_at=now,
                attempts=Job.attempts + 1,
                updated_at=now,
            )
            .returning(Job.id)
        )
        if job_id is None:
            return None
        return self.session.get(Job, job_id)

    def heartbeat(self, job: Job, owner: str, lease_seconds: int) -> None:
        if job.lease_owner != owner or job.status != "running":
            raise ValueError("Worker does not own the running job")
        now = utcnow()
        job.heartbeat_at = now
        job.lease_until = now + timedelta(seconds=lease_seconds)
        job.updated_at = now

    def done(self, job: Job, owner: str) -> None:
        if job.lease_owner != owner:
            raise ValueError("Worker does not own the job")
        job.status = "done"
        job.lease_until = None
        job.updated_at = utcnow()

    def park(self, job: Job, owner: str) -> None:
        """Set a leased job aside because its batch was paused; resume puts it back."""

        if job.lease_owner != owner:
            raise ValueError("Worker does not own the job")
        job.status = "paused"
        job.lease_owner = None
        job.lease_until = None
        job.attempts = max(0, job.attempts - 1)  # a pause is not a failed attempt
        job.updated_at = utcnow()

    def fail(self, job: Job, owner: str, error: str, max_attempts: int) -> None:
        if job.lease_owner != owner:
            raise ValueError("Worker does not own the job")
        job.last_error = error
        job.lease_until = None
        job.status = "failed" if job.attempts >= max_attempts else "queued"
        job.run_after = utcnow() + timedelta(seconds=min(2**job.attempts, 30))
        job.updated_at = utcnow()
