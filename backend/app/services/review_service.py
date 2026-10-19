from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
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
from app.extract.service import extract_document
from app.services.batch_service import BatchUseCases
from app.services.fixture_service import FixtureStore
from app.services.rubric_service import RubricUseCases


class ReviewUseCases:
    def __init__(self, session: Session, fixtures: FixtureStore) -> None:
        self.session = session
        self.fixtures = fixtures

    def open(self, submission_id: str, actor_id: str) -> dict[str, Any]:
        submission = self.session.get(Submission, submission_id)
        if submission is None:
            raise KeyError(submission_id)
        if submission.status == SubmissionStatus.AI_DONE.value:
            submission.status = SubmissionStatus.IN_REVIEW.value
            submission.claimed_by = actor_id
            submission.version += 1
            self.session.flush()
        stored_file = self.session.get(File, submission.file_id) if submission.file_id else None
        if stored_file and not submission.document_json:
            try:
                document = extract_document(Path(stored_file.path), submission.id, stored_file.mime)
                submission.document_json = json.dumps(document, ensure_ascii=False)
                submission.word_count = document["word_count"]
                submission.text_quality = "text_layer"
                submission.document_version = int(document["version"])
                stored_file.pages = int(document["page_count"])
                stored_file.text_layer = True
                submission.is_mock = False
                self.session.flush()
            except (OSError, ValueError):
                pass
        if submission.document_json:
            batch = self._batch(submission.batch_id)
            rubric = self.session.get(Rubric, batch.rubric_library_id)
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
            return {
                "submission": {
                    "id": submission.id,
                    "batch_id": submission.batch_id,
                    "sid": submission.sid,
                    "filename": stored_file.original_name if stored_file else submission.id,
                    "status": submission.status,
                    "progress": submission.ai_summary,
                    "error": submission.error_reason,
                    "version": submission.version,
                },
                "batch": {
                    "id": batch.id,
                    "name": batch.name,
                    "status": batch.status,
                    "counts": BatchUseCases(self.session).counts(batch.id),
                },
                "document": json.loads(submission.document_json),
                "rubric": {
                    "id": batch.rubric_library_id,
                    "version": batch.rubric_version,
                    "title": rubric.title if rubric else "Imported rubric",
                    "criteria": [
                        {
                            "definition": RubricUseCases._criterion(definition),
                            "ai_score": results[definition.id].score
                            if definition.id in results
                            else reviews[definition.id].score,
                            "score": reviews[definition.id].score,
                            "confidence": results[definition.id].confidence
                            if definition.id in results
                            else submission.min_confidence or "medium",
                            "sufficiency": results[definition.id].sufficiency
                            if definition.id in results
                            else "unknown",
                            "coverage": json.loads(results[definition.id].coverage_json or "[]")
                            if definition.id in results
                            else [],
                            "status": reviews[definition.id].status,
                            "rationale": results[definition.id].rationale
                            if definition.id in results
                            else "No AI grading result is available for this criterion.",
                            "comment": reviews[definition.id].comment,
                            "evidence_ids": [
                                evidence.id
                                for evidence in evidence_by_criterion.get(definition.id, [])
                            ],
                            "version": reviews[definition.id].version,
                        }
                        for definition in definitions
                        if definition.id in reviews
                    ],
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
                "can_edit": True,
                "claim": {
                    "marker_id": actor_id,
                    "marker_name": "J. Alvarez",
                    "expires_at": None,
                },
                "_mock": False,
            }
        fixture_path = self.fixtures.root / "reviews" / f"{submission_id}.json"
        if not fixture_path.exists() and submission.is_mock:
            fixture_path = self.fixtures.root / "reviews" / "shared-sample.json"
        if fixture_path.exists():
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            batch = self._batch(submission.batch_id)
            payload["submission"]["id"] = submission.id
            payload["submission"]["batch_id"] = submission.batch_id
            payload["submission"]["sid"] = submission.sid
            payload["submission"]["filename"] = (
                stored_file.original_name
                if stored_file
                else f"{submission.sid or submission.id}.pdf"
            )
            payload["submission"]["status"] = submission.status
            payload["submission"]["version"] = submission.version
            payload["batch"] = {
                "id": batch.id,
                "name": batch.name,
                "status": batch.status,
                "counts": BatchUseCases(self.session).counts(batch.id),
            }
            if fixture_path.name == "shared-sample.json" and batch.rubric_library_id:
                rubric = self.session.get(Rubric, batch.rubric_library_id)
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
                payload["rubric"] = {
                    "id": batch.rubric_library_id,
                    "version": batch.rubric_version,
                    "title": rubric.title if rubric else "Imported rubric",
                    "criteria": [
                        {
                            "definition": RubricUseCases._criterion(definition),
                            "ai_score": reviews[definition.id].score,
                            "score": reviews[definition.id].score,
                            "confidence": submission.min_confidence or "medium",
                            "sufficiency": "unknown",
                            "coverage": [],
                            "status": reviews[definition.id].status,
                            "rationale": "Deterministic local FakeLLM suggestion for this rubric criterion.",
                            "comment": reviews[definition.id].comment,
                            "evidence_ids": [],
                            "version": reviews[definition.id].version,
                        }
                        for definition in definitions
                        if definition.id in reviews
                    ],
                }
                payload["evidence"] = []
                payload["document"]["title"] = "Demo sample essay"
                payload["document"]["content_url"] = None
            payload["_mock"] = bool(submission.is_mock)
            if submission.is_mock:
                payload["demo_banner"] = "Demo sample content — not this student's real work"
            return payload
        raise KeyError(f"review:{submission_id}")

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
        submission.final_level = level_for_score(submission.final_total).value
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
        next_id = self.session.scalar(
            select(Submission.id)
            .where(
                Submission.batch_id == batch.id,
                Submission.status.in_(
                    [SubmissionStatus.AI_DONE.value, SubmissionStatus.IN_REVIEW.value]
                ),
                Submission.id != submission.id,
            )
            .order_by(Submission.id)
            .limit(1)
        )
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

    def _counts(self, batch_id: str) -> CompletionCounts:
        rows = dict(
            self.session.execute(
                select(Submission.status, func.count())
                .where(Submission.batch_id == batch_id)
                .group_by(Submission.status)
            ).all()
        )
        batch = self._batch(batch_id)
        ready = rows.get("ai_done", 0) + rows.get("in_review", 0)
        processing_states = {
            "uploaded",
            "extracting",
            "needs_ocr",
            "ocr_running",
            "queued",
            "marking",
        }
        return CompletionCounts(
            total=batch.total_count,
            confirmed=rows.get("confirmed", 0),
            excluded=rows.get("excluded", 0),
            ready=ready,
            processing=sum(rows.get(state, 0) for state in processing_states),
            failed=rows.get("failed", 0),
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
