from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.audit import AuditLog
from app.db.models.batch import Batch
from app.db.models.job import Job
from app.db.models.llm import LLMCall
from app.db.models.review import Review
from app.db.models.rubric import Rubric, RubricCriterion
from app.db.models.submission import AIResult, Evidence, File, Submission
from app.domain.ids import new_id
from app.domain.states import BatchStatus, SubmissionStatus
from app.jobs.queue import JobQueue


class BatchUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        batch = Batch(
            id=new_id("bat"),
            name=payload["name"],
            unit=payload.get("unit"),
            term_id=payload["term_id"],
            due_at=_dt(payload.get("due_at")),
            status=BatchStatus.DRAFT.value,
            rubric_library_id=payload.get("rubric_id"),
            rubric_version=payload.get("rubric_version"),
            total_count=0,
            created_by=actor_id,
            created_at=now,
            version=1,
        )
        self.session.add(batch)
        self.session.flush()
        return {"batch": self.serialize(batch)}

    def start(
        self,
        batch_id: str,
        payload: dict[str, Any],
        sample: int | None,
        runtime_settings: Settings,
    ) -> dict[str, Any]:
        batch = self._batch(batch_id)
        if batch.status != BatchStatus.DRAFT.value:
            return {
                "batch_id": batch.id,
                "status": batch.status,
                "job_id": None,
                "sample_size": sample,
                "queued": 0,
                "counts": self.counts(batch.id),
            }
        provider = payload.get("provider") or runtime_settings.llm
        if provider not in {"fake", "university"} and not payload.get(
            "external_processing_acknowledged"
        ):
            raise ValueError("External-provider acknowledgement is required")
        unresolved = (
            self.session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.batch_id == batch.id,
                    (Submission.sid.is_(None)) | (Submission.status == "duplicate"),
                )
            )
            or 0
        )
        if unresolved:
            raise ValueError("manifest_unresolved")
        submissions = (
            list(
                self.session.scalars(
                    select(Submission)
                    .where(
                        Submission.batch_id == batch.id,
                        Submission.status == SubmissionStatus.UPLOADED.value,
                    )
                    .order_by(Submission.id)
                    .limit(sample)
                )
            )
            if sample
            else list(
                self.session.scalars(
                    select(Submission).where(
                        Submission.batch_id == batch.id,
                        Submission.status == SubmissionStatus.UPLOADED.value,
                    )
                )
            )
        )
        batch.status = BatchStatus.PROCESSING.value
        batch.started_at = datetime.now(timezone.utc)
        batch.model_provider = provider
        batch.model_name = payload.get("model") or runtime_settings.ai_model
        batch.prompt_version = "criterion-grade-coverage-v3"
        batch.external_processing_acknowledged = bool(
            payload.get("external_processing_acknowledged", False)
        )
        batch.version += 1
        progress_job = JobQueue(self.session).enqueue(
            "demo_progress",
            {
                "batch_id": batch.id,
                "status": "processing",
                "counts": self.counts(batch.id),
                "eta_seconds": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        criteria = list(
            self.session.scalars(
                select(RubricCriterion)
                .where(
                    RubricCriterion.rubric_id == batch.rubric_library_id,
                    RubricCriterion.rubric_version == batch.rubric_version,
                )
                .order_by(RubricCriterion.position)
            )
        )
        rubric = self.session.get(Rubric, batch.rubric_library_id)
        batch.rubric_snapshot_json = json.dumps(
            {
                "id": batch.rubric_library_id,
                "version": batch.rubric_version,
                "title": rubric.title if rubric else "Imported rubric",
                "source": rubric.source if rubric else "Imported",
                "criteria": [
                    {
                        "id": criterion.id,
                        "name": criterion.name,
                        "weight": criterion.weight,
                        "levels": json.loads(criterion.levels_json or "[]"),
                        "grading_mode": criterion.grading_mode,
                        "aspects": json.loads(criterion.aspects_json or "[]"),
                    }
                    for criterion in criteria
                ],
            },
            ensure_ascii=False,
        )
        grade_jobs = []
        for submission in submissions:
            submission.status = SubmissionStatus.QUEUED.value
            submission.ai_summary = "Queued for extraction and AI grading"
            submission.version += 1
            grade_jobs.append(
                JobQueue(self.session).enqueue(
                    "grade",
                    {
                        "batch_id": batch.id,
                        "submission_id": submission.id,
                        "rubric_id": batch.rubric_library_id,
                        "rubric_version": batch.rubric_version,
                    },
                )
            )
        self.session.flush()
        return {
            "batch_id": batch.id,
            "status": batch.status,
            "job_id": grade_jobs[0].id if grade_jobs else progress_job.id,
            "job_ids": [item.id for item in grade_jobs],
            "sample_size": sample,
            "queued": len(submissions),
            "counts": self.counts(batch.id),
        }

    def finalise(self, batch_id: str, actor_id: str, version: int) -> dict[str, Any]:
        batch = self._batch(batch_id)
        if batch.version != version:
            raise RuntimeError("version_conflict")
        counts = self.counts(batch_id)
        if batch.status != BatchStatus.COMPLETED.value or counts["failed"]:
            raise RuntimeError("batch_incomplete")
        batch.status = BatchStatus.FINALISED.value
        batch.finalised_at = datetime.now(timezone.utc)
        batch.version += 1
        self._audit(actor_id, "batch.finalise", batch)
        return {
            "batch_id": batch.id,
            "status": batch.status,
            "locked": True,
            "finalised_at": batch.finalised_at.isoformat(),
            "version": batch.version,
        }

    def reopen(self, batch_id: str, actor_id: str, reason: str, version: int) -> dict[str, Any]:
        batch = self._batch(batch_id)
        if batch.version != version:
            raise RuntimeError("version_conflict")
        if batch.status != BatchStatus.FINALISED.value:
            raise RuntimeError("invalid_transition")
        batch.status = BatchStatus.COMPLETED.value
        batch.finalised_at = None
        batch.version += 1
        self._audit(
            actor_id, "batch.reopen", batch, {"reason": reason, "exports_invalidated": True}
        )
        return {
            "batch_id": batch.id,
            "status": batch.status,
            "locked": False,
            "reopened_at": datetime.now(timezone.utc).isoformat(),
            "version": batch.version,
        }

    def cancel(self, batch_id: str, actor_id: str, reason: str, version: int) -> dict[str, Any]:
        batch = self._batch(batch_id)
        if batch.version != version:
            raise RuntimeError("version_conflict")
        if batch.status not in {
            BatchStatus.DRAFT.value,
            BatchStatus.PROCESSING.value,
            BatchStatus.FAILED_ALL.value,
        }:
            raise RuntimeError("invalid_transition")
        before = batch.status
        batch.status = BatchStatus.CANCELLED.value
        batch.version += 1
        active_submission_states = [
            SubmissionStatus.UPLOADED.value,
            SubmissionStatus.EXTRACTING.value,
            SubmissionStatus.NEEDS_OCR.value,
            SubmissionStatus.OCR_RUNNING.value,
            SubmissionStatus.QUEUED.value,
            SubmissionStatus.MARKING.value,
        ]
        submissions = list(
            self.session.scalars(
                select(Submission).where(
                    Submission.batch_id == batch.id,
                    Submission.status.in_(active_submission_states),
                )
            )
        )
        for submission in submissions:
            submission.status = SubmissionStatus.CANCELLED.value
            submission.error_reason = reason or "Batch terminated by user"
            submission.ai_summary = "Cancelled"
            submission.version += 1
        self.session.execute(
            update(Job)
            .where(Job.batch_id == batch.id, Job.status == "queued")
            .values(
                status="cancelled",
                last_error=reason or "Batch terminated by user",
                updated_at=datetime.now(timezone.utc),
            )
        )
        self._audit(
            actor_id,
            "batch.cancel",
            batch,
            {"before_status": before, "reason": reason or "Batch terminated by user"},
        )
        return {
            "batch_id": batch.id,
            "status": batch.status,
            "cancelled_submissions": len(submissions),
            "version": batch.version,
        }

    def delete(self, batch_id: str, actor_id: str, version: int) -> dict[str, Any]:
        batch = self._batch(batch_id)
        if batch.version != version:
            raise RuntimeError("version_conflict")
        if batch.status == BatchStatus.FINALISED.value:
            raise RuntimeError("finalised_batch_locked")
        if batch.status == BatchStatus.PROCESSING.value:
            raise RuntimeError("batch_must_be_cancelled")

        submissions = list(
            self.session.scalars(select(Submission).where(Submission.batch_id == batch.id))
        )
        submission_ids = [item.id for item in submissions]
        files = list(self.session.scalars(select(File).where(File.batch_id == batch.id)))
        ai_results = (
            list(
                self.session.scalars(
                    select(AIResult).where(AIResult.submission_id.in_(submission_ids))
                )
            )
            if submission_ids
            else []
        )
        ai_result_ids = [item.id for item in ai_results]
        if ai_result_ids:
            self.session.execute(delete(Evidence).where(Evidence.ai_result_id.in_(ai_result_ids)))
        if submission_ids:
            self.session.execute(delete(Review).where(Review.submission_id.in_(submission_ids)))
            self.session.execute(delete(AIResult).where(AIResult.submission_id.in_(submission_ids)))
            self.session.execute(delete(LLMCall).where(LLMCall.submission_id.in_(submission_ids)))
        self.session.execute(delete(Job).where(Job.batch_id == batch.id))
        self.session.execute(delete(Submission).where(Submission.batch_id == batch.id))
        self.session.execute(delete(File).where(File.batch_id == batch.id))
        self.session.delete(batch)
        self.session.add(
            AuditLog(
                id=new_id("aud"),
                actor=actor_id,
                action="batch.delete",
                entity="batch",
                entity_id=batch_id,
                before_json=json.dumps({"name": batch.name, "status": batch.status}),
                after_json=json.dumps({"deleted": True}),
                created_at=datetime.now(timezone.utc),
            )
        )
        return {
            "deleted": True,
            "batch_id": batch_id,
            "file_paths": [item.path for item in files],
        }

    def counts(self, batch_id: str) -> dict[str, int]:
        rows = dict(
            self.session.execute(
                select(Submission.status, func.count())
                .where(Submission.batch_id == batch_id)
                .group_by(Submission.status)
            ).all()
        )
        batch = self._batch(batch_id)
        processing = sum(
            rows.get(s, 0) for s in ("uploaded", "extracting", "ocr_running", "queued", "marking")
        )
        ready = rows.get("ai_done", 0) + rows.get("in_review", 0)
        low_confidence = (
            self.session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.batch_id == batch_id,
                    Submission.status.in_(["ai_done", "in_review"]),
                    Submission.min_confidence == "low",
                )
            )
            or 0
        )
        needs_manual = rows.get("needs_ocr", 0)
        return {
            "total": batch.total_count,
            "processed": ready + rows.get("confirmed", 0) + needs_manual,
            "ready": ready,
            "low_confidence": low_confidence,
            "needs_manual": needs_manual,
            "processing": processing,
            "confirmed": rows.get("confirmed", 0),
            "adjusted": 0,
            "failed": rows.get("failed", 0),
            "excluded": rows.get("excluded", 0),
            "cancelled": rows.get("cancelled", 0),
        }

    def serialize(self, batch: Batch) -> dict[str, Any]:
        rubric_summary = None
        if batch.rubric_library_id:
            rubric = self.session.get(Rubric, batch.rubric_library_id)
            if rubric:
                criteria_count = (
                    self.session.scalar(
                        select(func.count())
                        .select_from(RubricCriterion)
                        .where(
                            RubricCriterion.rubric_id == batch.rubric_library_id,
                            RubricCriterion.rubric_version == batch.rubric_version,
                        )
                    )
                    or 0
                )
                total_weight = (
                    self.session.scalar(
                        select(func.sum(RubricCriterion.weight)).where(
                            RubricCriterion.rubric_id == batch.rubric_library_id,
                            RubricCriterion.rubric_version == batch.rubric_version,
                        )
                    )
                    or 0
                )
                rubric_summary = {
                    "id": rubric.id,
                    "version": batch.rubric_version,
                    "title": rubric.title,
                    "source": rubric.source,
                    "criteria_count": criteria_count,
                    "total_weight": float(total_weight),
                    "used_by_count": 1,
                    "updated_at": rubric.updated_at.isoformat(),
                }
        return {
            "id": batch.id,
            "name": batch.name,
            "unit": batch.unit,
            "term": {"id": batch.term_id, "label": "Semester 2, 2026"},
            "due_at": batch.due_at.isoformat() if batch.due_at else None,
            "status": batch.status,
            "display_status": "processing"
            if self.counts(batch.id)["processing"] > 0
            else batch.status,
            "rubric": rubric_summary,
            "counts": self.counts(batch.id),
            "eta_seconds": None,
            "created_at": batch.created_at.isoformat(),
            "started_at": _iso(batch.started_at),
            "completed_at": _iso(batch.completed_at),
            "finalised_at": _iso(batch.finalised_at),
            "version": batch.version,
        }

    def _batch(self, batch_id: str) -> Batch:
        batch = self.session.get(Batch, batch_id)
        if batch is None:
            raise KeyError(batch_id)
        return batch

    def _audit(
        self, actor: str, action: str, batch: Batch, extra: dict[str, Any] | None = None
    ) -> None:
        self.session.add(
            AuditLog(
                id=new_id("aud"),
                actor=actor,
                action=action,
                entity="batch",
                entity_id=batch.id,
                before_json=None,
                after_json=json.dumps({"status": batch.status, **(extra or {})}),
                created_at=datetime.now(timezone.utc),
            )
        )


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
