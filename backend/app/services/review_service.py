from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models.audit import AuditLog
from app.db.models.batch import Batch
from app.db.models.review import Review
from app.db.models.rubric import Rubric, RubricCriterion
from app.db.models.submission import AIResult, Evidence, File, Submission
from app.domain.bands import level_for_score
from app.domain.completion import CompletionCounts, is_complete
from app.domain.ids import new_id
from app.domain.states import BatchStatus, SubmissionStatus
from app.services.batch_service import BatchUseCases
from app.services.rubric_service import RubricUseCases
from app.services.submission_service import apply_extraction, marker_names

READY_STATES = [SubmissionStatus.AI_DONE.value, SubmissionStatus.IN_REVIEW.value]
MANUAL_STATES = [SubmissionStatus.NEEDS_OCR.value, SubmissionStatus.OCR_FAILED.value]


class ReviewUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session

    def open(self, submission_id: str, actor_id: str) -> dict[str, Any]:
        submission = self.session.get(Submission, submission_id)
        if submission is None:
            raise KeyError(submission_id)
        batch = self._batch(submission.batch_id)
        if submission.status == SubmissionStatus.AI_DONE.value:
            submission.status = SubmissionStatus.IN_REVIEW.value
            submission.claimed_by = actor_id
            submission.version += 1
            self.session.flush()
        stored_file = self.session.get(File, submission.file_id) if submission.file_id else None
        if stored_file and not submission.document_json:
            try:
                apply_extraction(self.session, submission, stored_file)
            except (OSError, ValueError):
                pass
        definitions = list(
            self.session.scalars(
                select(RubricCriterion)
                .where(
                    RubricCriterion.rubric_id == batch.rubric_library_id,
                    RubricCriterion.rubric_version == batch.rubric_version,
                )
                .order_by(RubricCriterion.position)
            )
        )
        reviews = {
            item.criterion_id: item
            for item in self.session.scalars(
                select(Review).where(Review.submission_id == submission.id)
            )
        }
        manual = submission.status in {
            SubmissionStatus.NEEDS_OCR.value,
            SubmissionStatus.OCR_FAILED.value,
        }
        if manual:
            # No AI result can exist without text; give the tutor empty criteria to mark.
            now = datetime.now(timezone.utc)
            for definition in definitions:
                if definition.id not in reviews:
                    review = Review(
                        id=new_id("rev"),
                        submission_id=submission.id,
                        criterion_id=definition.id,
                        score=None,
                        comment="",
                        status="manual",
                        updated_by=actor_id,
                        updated_at=now,
                        version=1,
                    )
                    self.session.add(review)
                    reviews[definition.id] = review
            self.session.flush()
        rubric = self.session.get(Rubric, batch.rubric_library_id)
        results = {
            item.criterion_id: item
            for item in self.session.scalars(
                select(AIResult)
                .where(AIResult.submission_id == submission.id)
                .order_by(AIResult.created_at)
            )
        }
        evidence_rows = (
            list(
                self.session.scalars(
                    select(Evidence).where(
                        Evidence.ai_result_id.in_([item.id for item in results.values()])
                    )
                )
            )
            if results
            else []
        )
        criterion_by_result = {item.id: criterion_id for criterion_id, item in results.items()}
        evidence_by_criterion: dict[str, list[Evidence]] = {}
        for evidence in evidence_rows:
            criterion_id = criterion_by_result.get(evidence.ai_result_id)
            if criterion_id:
                evidence_by_criterion.setdefault(criterion_id, []).append(evidence)
        document = (
            json.loads(submission.document_json)
            if submission.document_json
            else {
                "id": f"doc_{submission.id}",
                "version": submission.document_version,
                "page_count": stored_file.pages if stored_file else 0,
                "word_count": 0,
                "content_url": f"/api/v1/submissions/{submission.id}/file" if stored_file else None,
                "mime_type": stored_file.mime if stored_file else None,
                "title": stored_file.original_name if stored_file else submission.id,
                "paragraphs": [],
            }
        )
        users = marker_names(self.session)
        claimant = submission.claimed_by or actor_id
        criteria = []
        for definition in definitions:
            review = reviews.get(definition.id)
            if review is None:
                continue
            result = results.get(definition.id)
            criteria.append(
                {
                    "definition": RubricUseCases._criterion(definition),
                    "ai_score": result.score if result else None,
                    "ai_level": result.level if result else None,
                    "score": review.score,
                    "confidence": result.confidence if result else "none",
                    "sufficiency": result.sufficiency if result else "unknown",
                    "coverage": json.loads(result.coverage_json or "[]") if result else [],
                    "status": review.status,
                    "rationale": result.rationale
                    if result
                    else "No AI suggestion: this submission has no readable text, so it needs manual marking.",
                    "comment": review.comment,
                    "evidence_ids": [
                        evidence.id for evidence in evidence_by_criterion.get(definition.id, [])
                    ],
                    "version": review.version,
                }
            )
        return {
            "submission": {
                "id": submission.id,
                "batch_id": submission.batch_id,
                "sid": submission.sid,
                "filename": stored_file.original_name if stored_file else submission.id,
                "status": submission.status,
                "progress": submission.ai_summary,
                "error": submission.error_reason,
                "flags": json.loads(submission.flags_json or "[]"),
                "needs_manual": manual,
                "version": submission.version,
            },
            "batch": {
                "id": batch.id,
                "name": batch.name,
                "status": batch.status,
                "is_sample": bool(batch.is_sample),
                "counts": BatchUseCases(self.session).counts(batch.id),
            },
            "document": document,
            "rubric": {
                "id": batch.rubric_library_id,
                "version": batch.rubric_version,
                "title": rubric.title if rubric else "Imported rubric",
                "criteria": criteria,
            },
            "evidence": [
                {
                    "id": evidence.id,
                    "criterion_id": criterion_by_result[evidence.ai_result_id],
                    "document_version": evidence.document_version,
                    "page": evidence.page,
                    "paragraph": evidence.para,
                    "start_offset": evidence.char_start,
                    "end_offset": evidence.char_end,
                    "quote": evidence.quote,
                    "label": evidence.role,
                }
                for evidence in evidence_rows
                if evidence.ai_result_id in criterion_by_result and evidence.valid
            ],
            "can_edit": batch.status != BatchStatus.FINALISED.value,
            "claim": {
                "marker_id": claimant,
                "marker_name": users.get(claimant, claimant),
                "expires_at": submission.claimed_until.isoformat()
                if submission.claimed_until
                else None,
            },
        }

    def save_criterion(
        self, submission_id: str, criterion_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        submission = self._submission(submission_id)
        batch = self._batch(submission.batch_id)
        if batch.status == BatchStatus.FINALISED.value:
            raise PermissionError("submission_locked")
        review = self.session.scalar(
            select(Review).where(
                Review.submission_id == submission_id, Review.criterion_id == criterion_id
            )
        )
        if review is None:
            raise KeyError(criterion_id)
        if payload["version"] != review.version:
            raise RuntimeError("version_conflict")
        review.score = payload.get("score")
        review.comment = payload.get("comment", "")
        review.status = "edited"
        review.version += 1
        review.updated_at = datetime.now(timezone.utc)
        submission.version += 1
        if submission.status == SubmissionStatus.CONFIRMED.value:
            submission.status = SubmissionStatus.IN_REVIEW.value
            submission.confirmed_at = None
            submission.confirmed_by = None
            batch.status = BatchStatus.IN_REVIEW.value
            batch.completed_at = None
            batch.version += 1
        self.session.flush()
        return {
            "criterion_id": criterion_id,
            "score": review.score,
            "comment": review.comment,
            "status": review.status,
            "version": review.version,
            "saved_at": review.updated_at.isoformat(),
            "submission_total": self._review_total(submission_id),
            "submission_version": submission.version,
        }

    def confirm(self, submission_id: str, actor_id: str, version: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        submission = self._submission(submission_id)
        batch = self._batch(submission.batch_id)
        if batch.status == BatchStatus.FINALISED.value:
            raise PermissionError("submission_locked")
        if submission.status == SubmissionStatus.CONFIRMED.value:
            return self._confirm_response(submission, batch)
        if version != submission.version:
            raise RuntimeError("version_conflict")
        reviews = list(
            self.session.scalars(select(Review).where(Review.submission_id == submission_id))
        )
        if not reviews or any(item.score is None for item in reviews):
            raise ValueError("All criterion scores are required")
        for item in reviews:
            item.status = "confirmed"
            item.updated_at = now
            item.updated_by = actor_id
            item.version += 1
        before = {"status": submission.status, "final_total": submission.final_total}
        submission.final_total = sum(float(item.score or 0) for item in reviews)
        submission.final_level = level_for_score(submission.final_total, self._maximum(batch)).value
        submission.status = SubmissionStatus.CONFIRMED.value
        submission.confirmed_by = actor_id
        submission.confirmed_at = now
        submission.version += 1
        # SessionLocal intentionally disables autoflush so reads cannot trigger
        # surprise writes. Completion therefore needs this explicit boundary.
        self.session.flush()
        counts = self._counts(batch.id)
        if is_complete(counts):
            batch.status = BatchStatus.COMPLETED.value
            batch.completed_at = now
            batch.version += 1
        self.session.add(
            AuditLog(
                id=new_id("aud"),
                actor=actor_id,
                action="submission.confirm",
                entity="submission",
                entity_id=submission.id,
                before_json=json.dumps(before),
                after_json=json.dumps(
                    {"status": submission.status, "final_total": submission.final_total}
                ),
                created_at=now,
            )
        )
        self.session.flush()
        return self._confirm_response(submission, batch)

    def _confirm_response(self, submission: Submission, batch: Batch) -> dict[str, Any]:
        counts = self._counts(batch.id)
        upcoming = self.queue(batch.id, limit=1, exclude={submission.id})
        next_id = upcoming[0].id if upcoming else None
        return {
            "submission_id": submission.id,
            "status": submission.status,
            "confirmed_at": submission.confirmed_at.isoformat()
            if submission.confirmed_at
            else None,
            "next_id": next_id,
            "batch_status": batch.status,
            "remaining": {
                "ready": counts.ready,
                "processing": counts.processing,
                "failed": counts.failed,
            },
        }

    def queue(
        self,
        batch_id: str | None = None,
        *,
        limit: int = 5,
        exclude: set[str] | None = None,
        after: str | None = None,
    ) -> list[Submission]:
        """Review order: low confidence first, then medium and high, then manual marking."""

        confidence_rank = case(
            (Submission.min_confidence == "low", 0),
            (Submission.min_confidence == "medium", 1),
            (Submission.min_confidence == "high", 2),
            else_=3,
        )
        manual_rank = case((Submission.status.in_(MANUAL_STATES), 1), else_=0)
        statement = (
            select(Submission)
            .join(Batch, Batch.id == Submission.batch_id)
            .where(
                Submission.status.in_(READY_STATES + MANUAL_STATES),
                Batch.status != BatchStatus.FINALISED.value,
            )
            .order_by(
                Batch.pinned.desc(),
                Batch.created_at.desc(),
                manual_rank,
                confidence_rank,
                Submission.sid,
                Submission.id,
            )
        )
        if batch_id:
            statement = statement.where(Submission.batch_id == batch_id)
        items = [
            item for item in self.session.scalars(statement) if item.id not in (exclude or set())
        ]
        if after:
            ids = [item.id for item in items]
            if after in ids:
                items = items[ids.index(after) + 1 :]
        return items[:limit]

    def _counts(self, batch_id: str) -> CompletionCounts:
        counts = BatchUseCases(self.session).counts(batch_id)
        return CompletionCounts(
            total=counts["total"],
            confirmed=counts["confirmed"],
            excluded=counts["excluded"],
            ready=counts["ready"],
            processing=counts["processing"] + counts["not_started"],
            failed=counts["failed"],
        )

    def _maximum(self, batch: Batch) -> float:
        return float(
            self.session.scalar(
                select(func.sum(RubricCriterion.weight)).where(
                    RubricCriterion.rubric_id == batch.rubric_library_id,
                    RubricCriterion.rubric_version == batch.rubric_version,
                )
            )
            or 0
        )

    def _review_total(self, submission_id: str) -> float | None:
        values = list(
            self.session.scalars(select(Review.score).where(Review.submission_id == submission_id))
        )
        return (
            None
            if not values or any(value is None for value in values)
            else sum(float(v) for v in values if v is not None)
        )

    def _submission(self, submission_id: str) -> Submission:
        value = self.session.get(Submission, submission_id)
        if value is None:
            raise KeyError(submission_id)
        return value

    def _batch(self, batch_id: str) -> Batch:
        value = self.session.get(Batch, batch_id)
        if value is None:
            raise KeyError(batch_id)
        return value
