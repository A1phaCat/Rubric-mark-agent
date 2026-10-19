from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
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
        job = self.session.scalar(
            select(Job)
            .where(
                Job.run_after <= now,
                or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now)),
            )
            .order_by(Job.created_at)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "running"
        job.lease_owner = owner
        job.lease_until = now + timedelta(seconds=lease_seconds)
        job.heartbeat_at = now
        job.attempts += 1
        job.updated_at = now
        self.session.flush()
        return job

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

    def fail(self, job: Job, owner: str, error: str, max_attempts: int) -> None:
        if job.lease_owner != owner:
            raise ValueError("Worker does not own the job")
        job.last_error = error
        job.lease_until = None
        job.status = "failed" if job.attempts >= max_attempts else "queued"
        job.run_after = utcnow() + timedelta(seconds=min(2**job.attempts, 30))
        job.updated_at = utcnow()
