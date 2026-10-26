from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.audit import AuditLog
from app.db.models.batch import Batch
from app.db.models.core import Term
from app.db.models.job import Job
from app.db.models.llm import LLMCall
from app.db.models.review import Review
from app.db.models.rubric import Rubric, RubricCriterion
from app.db.models.submission import AIResult, Evidence, File, Submission
from app.domain.bands import band_ranges, level_for_score
from app.domain.ids import new_id
from app.domain.states import BatchStatus, SubmissionStatus
from app.domain.timefmt import iso_utc
from app.jobs.queue import JobQueue

PROCESSING_STATES = ("extracting", "ocr_running", "queued", "marking")
MAX_PINNED = 3  # Home shows the pinned batches, so the pin list is capped
NEEDS_MANUAL_STATES = ("needs_ocr", "ocr_failed")


class BatchUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _current_term_id(self) -> str:
        """The newest term in the database (same order GET /me reports)."""

        term = self.session.query(Term).order_by(Term.id.desc()).first()
        if term is None:
            raise ValueError("No term is configured; create one before adding batches")
        return term.id

    def create(
        self,
        payload: dict[str, Any],
        actor_id: str,
        *,
        batch_id: str | None = None,
        is_sample: bool = False,
    ) -> dict[str, Any]:
        """Create a draft batch. ``batch_id``/``is_sample`` are used only by the sample seeder."""

        now = datetime.now(timezone.utc)
        batch = Batch(
            id=batch_id or new_id("bat"),
            name=payload["name"],
            unit=payload.get("unit"),
            term_id=payload.get("term_id") or self._current_term_id(),
            due_at=_dt(payload.get("due_at")),
            status=BatchStatus.DRAFT.value,
            rubric_library_id=payload.get("rubric_id"),
            rubric_version=payload.get("rubric_version"),
            total_count=0,
            is_sample=is_sample,
            created_by=actor_id,
            created_at=now,
            version=1,
        )
        self.session.add(batch)
        self.session.flush()
        # A new batch goes straight to the top of Home; the oldest pin makes room for it.
        unpinned = self._pin(batch)
        return {"batch": self.serialize(batch), "unpinned": unpinned}

    def list(
        self,
        *,
        active: bool | None = None,
        term: str | None = None,
        status: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Pinned batches first, then the rest; newest first within each group."""

        statement = select(Batch).order_by(
            Batch.pinned.desc(), Batch.pinned_at.desc(), Batch.created_at.desc()
        )
        if term:
            statement = statement.where(Batch.term_id == term)
        if status:
            statement = statement.where(Batch.status == status)
        if active:
            statement = statement.where(
                Batch.status.not_in([BatchStatus.FINALISED.value, BatchStatus.CANCELLED.value])
            )
        if q:
            pattern = f"%{q.lower()}%"
            statement = statement.where(
                func.lower(Batch.name).like(pattern) | func.lower(Batch.unit).like(pattern)
            )
        batches = list(self.session.scalars(statement))
        start = (page - 1) * page_size
        return {
            "items": [self.serialize(item) for item in batches[start : start + page_size]],
            "page": page,
            "page_size": page_size,
            "total": len(batches),
        }

    def set_pinned(self, batch_id: str, pinned: bool) -> dict[str, Any]:
        """Pin or unpin. Pinning a fourth batch unpins the one pinned longest ago."""

        batch = self._batch(batch_id)
        unpinned: list[dict[str, str]] = []
        if pinned:
            unpinned = self._pin(batch)
        else:
            batch.pinned = False
            batch.pinned_at = None
            self.session.flush()
        return {"batch_id": batch.id, "pinned": batch.pinned, "unpinned": unpinned}

    def _pin(self, batch: Batch) -> list[dict[str, str]]:
        batch.pinned = True
        batch.pinned_at = datetime.now(timezone.utc)
        self.session.flush()
        pinned = list(
            self.session.scalars(
                select(Batch)
                .where(Batch.pinned.is_(True))
                .order_by(Batch.pinned_at.desc(), Batch.created_at.desc())
            )
        )
        released = []
        for other in pinned[MAX_PINNED:]:
            other.pinned = False
            other.pinned_at = None
            released.append({"batch_id": other.id, "name": other.name})
        self.session.flush()
        return released

    def snapshot_rubric(self, batch: Batch) -> list[RubricCriterion]:
        """Freeze the batch's rubric version into the batch and return its criteria."""

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
                        "description": criterion.description or "",
                        "levels": json.loads(criterion.levels_json or "[]"),
                        "grading_mode": criterion.grading_mode,
                        "aspects": json.loads(criterion.aspects_json or "[]"),
                    }
                    for criterion in criteria
                ],
            },
            ensure_ascii=False,
        )
        return criteria

    def refresh_status(self, batch_id: str) -> None:
        """Derive the batch lifecycle state from its submissions after processing changes."""

        batch = self.session.get(Batch, batch_id)
        if batch is None or batch.status in {
            BatchStatus.CANCELLED.value,
            BatchStatus.FINALISED.value,
            BatchStatus.DRAFT.value,
        }:
            return
        self.session.flush()
        counts = self.counts(batch_id)
        remaining = counts["total"] - counts["excluded"]
        if counts["processing"]:
            status = BatchStatus.PROCESSING.value
        elif remaining and counts["failed"] == remaining:
            status = BatchStatus.FAILED_ALL.value
        elif remaining and counts["confirmed"] == remaining:
            status = BatchStatus.COMPLETED.value
        else:
            status = BatchStatus.IN_REVIEW.value
        if status != batch.status:
            batch.status = status
            if status == BatchStatus.COMPLETED.value and batch.completed_at is None:
                batch.completed_at = datetime.now(timezone.utc)
            batch.version += 1

    def start(
        self,
        batch_id: str,
        payload: dict[str, Any],
        sample: int | None,
        runtime_settings: Settings,
    ) -> dict[str, Any]:
        batch = self._batch(batch_id)
        not_started = (
            self.session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.batch_id == batch.id,
                    Submission.status == SubmissionStatus.UPLOADED.value,
                )
            )
            or 0
        )
        # A draft starts normally; a started batch may continue only while some of its
        # uploads were left out of a dry run. Finalised or cancelled batches never restart.
        continuing = batch.status in {
            BatchStatus.IN_REVIEW.value,
            BatchStatus.PROCESSING.value,
            BatchStatus.COMPLETED.value,
        } and bool(not_started)
        if batch.status != BatchStatus.DRAFT.value and not continuing:
            return {
                "batch_id": batch.id,
                "status": batch.status,
                "job_id": None,
                "sample_size": sample,
                "queued": 0,
                "counts": self.counts(batch.id),
            }
        provider = payload.get("provider") or runtime_settings.llm
        if provider == "fake" and not runtime_settings.fake_llm_allowed:
            raise ValueError("The offline FakeLLM is available only in the test environment")
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
        batch.started_at = batch.started_at or datetime.now(timezone.utc)
        batch.model_provider = provider
        batch.model_name = payload.get("model") or runtime_settings.ai_model
        batch.prompt_version = "criterion-grade-coverage-v3"
        batch.external_processing_acknowledged = bool(
            payload.get("external_processing_acknowledged", False)
        )
        batch.version += 1
        if not continuing:
            self.snapshot_rubric(batch)
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
            "job_id": grade_jobs[0].id if grade_jobs else None,
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
        """Disjoint lifecycle counts plus subset flags (low_confidence, adjusted)."""

        rows = dict(
            self.session.execute(
                select(Submission.status, func.count())
                .where(Submission.batch_id == batch_id)
                .group_by(Submission.status)
            ).all()
        )
        batch = self._batch(batch_id)
        processing = sum(rows.get(state, 0) for state in PROCESSING_STATES)
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
        needs_manual = sum(rows.get(state, 0) for state in NEEDS_MANUAL_STATES)
        return {
            "total": batch.total_count,
            "processed": ready + rows.get("confirmed", 0) + needs_manual,
            "ready": ready,
            "low_confidence": low_confidence,
            "needs_manual": needs_manual,
            "processing": processing,
            "not_started": rows.get("uploaded", 0),
            "confirmed": rows.get("confirmed", 0),
            "adjusted": len(self.adjusted_submission_ids(batch_id)),
            "failed": rows.get("failed", 0),
            "excluded": rows.get("excluded", 0),
            "cancelled": rows.get("cancelled", 0),
        }

    def adjusted_submission_ids(self, batch_id: str) -> set[str]:
        """Confirmed submissions where the tutor's final mark differs from the AI on any criterion."""

        statement = (
            select(Submission.id)
            .join(Review, Review.submission_id == Submission.id)
            .join(
                AIResult,
                (AIResult.submission_id == Review.submission_id)
                & (AIResult.criterion_id == Review.criterion_id),
            )
            .where(
                Submission.batch_id == batch_id,
                Submission.status == SubmissionStatus.CONFIRMED.value,
                func.abs(Review.score - AIResult.score) > 0.001,
            )
            .distinct()
        )
        return set(self.session.scalars(statement))

    def serialize(self, batch: Batch) -> dict[str, Any]:
        rubric_summary = None
        maximum = 0.0
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
                maximum = float(
                    self.session.scalar(
                        select(func.sum(RubricCriterion.weight)).where(
                            RubricCriterion.rubric_id == batch.rubric_library_id,
                            RubricCriterion.rubric_version == batch.rubric_version,
                        )
                    )
                    or 0
                )
                used_by_count = (
                    self.session.scalar(
                        select(func.count())
                        .select_from(Batch)
                        .where(Batch.rubric_library_id == rubric.id)
                    )
                    or 0
                )
                rubric_summary = {
                    "id": rubric.id,
                    "version": batch.rubric_version,
                    "title": rubric.title,
                    "source": rubric.source,
                    "criteria_count": criteria_count,
                    "total_weight": maximum,
                    "used_by_count": used_by_count,
                    "updated_at": iso_utc(rubric.updated_at),
                }
        term = self.session.get(Term, batch.term_id)
        counts = self.counts(batch.id)
        return {
            "id": batch.id,
            "name": batch.name,
            "unit": batch.unit,
            "term": {"id": batch.term_id, "label": term.label if term else batch.term_id},
            "due_at": batch.due_at.isoformat() if batch.due_at else None,
            "status": batch.status,
            "display_status": "processing" if counts["processing"] > 0 else batch.status,
            "is_sample": bool(batch.is_sample),
            "pinned": bool(batch.pinned),
            "pinned_at": _iso(batch.pinned_at),
            "rubric": rubric_summary,
            "counts": counts,
            "insights": self._insights(batch.id, maximum),
            "model": {"provider": batch.model_provider, "name": batch.model_name}
            if batch.model_provider
            else None,
            "eta_seconds": None,
            "created_at": iso_utc(batch.created_at),
            "started_at": _iso(batch.started_at),
            "completed_at": _iso(batch.completed_at),
            "finalised_at": _iso(batch.finalised_at),
            "version": batch.version,
        }

    def _insights(self, batch_id: str, maximum: float) -> dict[str, Any]:
        """Confidence mix of AI-processed work and the grade mix of confirmed work."""

        processed_states = ["ai_done", "in_review", "confirmed"]
        confidence = dict(
            self.session.execute(
                select(Submission.min_confidence, func.count())
                .where(
                    Submission.batch_id == batch_id,
                    Submission.status.in_(processed_states),
                )
                .group_by(Submission.min_confidence)
            ).all()
        )
        confirmed = list(
            self.session.execute(
                select(Submission.final_total, Submission.ai_total).where(
                    Submission.batch_id == batch_id,
                    Submission.status == SubmissionStatus.CONFIRMED.value,
                    Submission.final_total.is_not(None),
                )
            ).all()
        )
        finals = [float(row[0]) for row in confirmed]
        ais = [float(row[1]) for row in confirmed if row[1] is not None]
        grades = {level.value: 0 for level, _lower, _upper in band_ranges()}
        for value in finals:
            grades[level_for_score(value, maximum).value] += 1
        return {
            "maximum": maximum,
            "confidence": {
                key: int(confidence.get(key, 0)) for key in ("high", "medium", "low", "none")
            },
            "grades": grades,
            "average_final": round(sum(finals) / len(finals), 1) if finals else None,
            "average_ai": round(sum(ais) / len(ais), 1) if ais else None,
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
    return iso_utc(value)
