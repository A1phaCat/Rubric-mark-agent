"""Read projections for the home dashboard, batch results, reports and CSV export.

Everything here is derived from submission, review and AI-result rows on every
request; nothing is cached or stored as a separate aggregate.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.batch import Batch
from app.db.models.review import Review
from app.db.models.rubric import RubricCriterion
from app.db.models.submission import AIResult, Evidence, File, Submission
from app.domain import levels
from app.domain.bands import BAND_NAMES, band_ranges, level_for_score, percent
from app.domain.states import BatchStatus, Level, SubmissionStatus
from app.domain.timefmt import iso_utc
from app.report import project_for_audience
from app.services.batch_service import BatchUseCases
from app.services.review_service import MANUAL_STATES, READY_STATES, ReviewUseCases
from app.services.submission_service import marker_names, submission_row


class AnalyticsUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ home
    def home_summary(self, user_id: str) -> dict[str, Any]:
        open_batches = list(
            self.session.scalars(
                select(Batch)
                .where(Batch.status.not_in([BatchStatus.FINALISED.value, BatchStatus.CANCELLED.value]))
                .order_by(Batch.pinned.desc(), Batch.created_at.desc())
            )
        )
        names = {batch.id: batch.name for batch in open_batches}

        def by_batch(condition: Any) -> dict[str, Any]:
            rows = list(
                self.session.execute(
                    select(Submission.batch_id, func.count())
                    .where(Submission.batch_id.in_(list(names)), condition)
                    .group_by(Submission.batch_id)
                ).all()
            )
            items = [
                {"batch_id": batch_id, "batch_name": names[batch_id], "count": int(count)}
                for batch_id, count in rows
            ]
            items.sort(key=lambda item: list(names).index(item["batch_id"]))
            return {"count": sum(item["count"] for item in items), "by_batch": items}

        ready = by_batch(Submission.status.in_(READY_STATES))
        upcoming = ReviewUseCases(self.session).queue(limit=1)
        ready["next_submission_id"] = upcoming[0].id if upcoming else None
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        confirmed_this_week = (
            self.session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.status == SubmissionStatus.CONFIRMED.value,
                    Submission.confirmed_at >= week_start,
                )
            )
            or 0
        )
        confirmed_by_me = (
            self.session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.status == SubmissionStatus.CONFIRMED.value,
                    Submission.confirmed_by == user_id,
                    Submission.confirmed_at >= week_start,
                )
            )
            or 0
        )
        return {
            "open_batches": len(open_batches),
            "batches_needing_review": len(ready["by_batch"]),
            "ready_for_review": ready,
            "low_confidence": by_batch(
                Submission.status.in_(READY_STATES) & (Submission.min_confidence == "low")
            ),
            "needs_manual": by_batch(Submission.status.in_(MANUAL_STATES)),
            "confirmed_this_week": {
                "count": int(confirmed_this_week),
                "by_me": int(confirmed_by_me),
                "week_started_at": week_start.isoformat(),
            },
        }

    def home_queue(self, limit: int) -> dict[str, Any]:
        items = ReviewUseCases(self.session).queue(limit=limit)
        batches = {item.batch_id: self.session.get(Batch, item.batch_id) for item in items}
        result = []
        for item in items:
            batch = batches[item.batch_id]
            manual = item.status in MANUAL_STATES
            weakest = None if manual else self._weakest_criterion(item.id)
            result.append(
                {
                    "submission_id": item.id,
                    "sid": item.sid,
                    "batch_id": item.batch_id,
                    "batch_name": batch.name if batch else item.batch_id,
                    "manual_reason": (
                        "too_long" if "too_long" in json.loads(item.flags_json or "[]") else "no_text_layer"
                    )
                    if manual
                    else None,
                    "reason": "needs_manual"
                    if manual
                    else "low_confidence"
                    if item.min_confidence == "low"
                    else "ready",
                    "criterion_id": weakest["id"] if weakest else None,
                    "criterion_name": weakest["name"] if weakest else None,
                    "confidence": None if manual else item.min_confidence,
                    "ai_total": item.ai_total,
                    "maximum": self._maximum(batch) if batch else None,
                }
            )
        return {"items": result, "limit": limit}

    def _weakest_criterion(self, submission_id: str) -> dict[str, str] | None:
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        rows = list(
            self.session.execute(
                select(AIResult.criterion_id, AIResult.confidence, RubricCriterion.name)
                .join(RubricCriterion, RubricCriterion.id == AIResult.criterion_id)
                .where(AIResult.submission_id == submission_id)
            ).all()
        )
        if not rows:
            return None
        criterion_id, _confidence, name = min(rows, key=lambda row: order.get(row[1], 0))
        return {"id": criterion_id, "name": name}

    # --------------------------------------------------------------- results
    def batch_results(self, batch_id: str) -> dict[str, Any]:
        batch = self.session.get(Batch, batch_id)
        if batch is None:
            raise KeyError(batch_id)
        service = BatchUseCases(self.session)
        maximum = self._maximum(batch)
        criteria = self._criteria(batch)
        submissions = list(
            self.session.scalars(
                select(Submission).where(Submission.batch_id == batch_id).order_by(Submission.sid, Submission.id)
            )
        )
        files = self._files(submissions)
        markers = marker_names(self.session)
        adjusted_ids = service.adjusted_submission_ids(batch_id)
        confirmed = [item for item in submissions if item.status == SubmissionStatus.CONFIRMED.value]
        finals = [float(item.final_total) for item in confirmed if item.final_total is not None]
        ais = [float(item.ai_total) for item in confirmed if item.ai_total is not None]
        distribution = []
        for level, lower, upper in band_ranges():
            count = sum(1 for value in finals if level_for_score(value, maximum) == level)
            distribution.append(
                {
                    "band": level.value,
                    "name": BAND_NAMES[level],
                    "min_percent": lower,
                    "max_percent": upper,
                    "min_score": round(maximum * lower / 100, 2),
                    "max_score": round(maximum * upper / 100, 2),
                    "count": count,
                }
            )
        reviews = list(
            self.session.scalars(
                select(Review).where(Review.submission_id.in_([item.id for item in confirmed]))
            )
        ) if confirmed else []
        results = list(
            self.session.scalars(
                select(AIResult).where(AIResult.submission_id.in_([item.id for item in confirmed]))
            )
        ) if confirmed else []
        ai_by_key = {(item.submission_id, item.criterion_id): item.score for item in results}
        criteria_summary = []
        for criterion in criteria:
            scores = [float(r.score) for r in reviews if r.criterion_id == criterion.id and r.score is not None]
            ai_scores = [
                float(ai_by_key[(r.submission_id, r.criterion_id)])
                for r in reviews
                if r.criterion_id == criterion.id and (r.submission_id, r.criterion_id) in ai_by_key
            ]
            changed = sum(
                1
                for r in reviews
                if r.criterion_id == criterion.id
                and (r.submission_id, r.criterion_id) in ai_by_key
                and r.score is not None
                and abs(float(r.score) - float(ai_by_key[(r.submission_id, r.criterion_id)])) > 0.001
            )
            criteria_summary.append(
                {
                    "criterion_id": criterion.id,
                    "name": criterion.name,
                    "max_score": criterion.weight,
                    "average_final": round(sum(scores) / len(scores), 2) if scores else None,
                    "average_ai": round(sum(ai_scores) / len(ai_scores), 2) if ai_scores else None,
                    "adjusted_count": changed,
                }
            )
        comments = sum(1 for r in reviews if (r.comment or "").strip())
        marker_ids = {item.confirmed_by for item in confirmed if item.confirmed_by}
        return {
            "batch": service.serialize(batch),
            "locked": batch.status == BatchStatus.FINALISED.value,
            "released_at": iso_utc(batch.finalised_at),
            "summary": {
                "maximum": maximum,
                "confirmed": len(confirmed),
                "average_final": round(sum(finals) / len(finals), 1) if finals else None,
                "average_ai": round(sum(ais) / len(ais), 1) if ais else None,
                "average_final_percent": round(percent(sum(finals) / len(finals), maximum), 1)
                if finals
                else None,
                "adjusted_count": len(adjusted_ids),
                "adjusted_percent": round(100 * len(adjusted_ids) / len(confirmed), 1)
                if confirmed
                else 0,
                "comments_count": comments,
                "marker_count": len(marker_ids),
                "markers": [{"id": marker, "name": markers.get(marker, marker)} for marker in sorted(marker_ids)],
            },
            "distribution": distribution,
            "criteria": criteria_summary,
            "submissions": {
                "items": [
                    submission_row(
                        item, files.get(item.file_id), markers, adjusted=item.id in adjusted_ids
                    )
                    for item in submissions
                ],
                "page": 1,
                "page_size": len(submissions),
                "total": len(submissions),
            },
        }

    def csv_rows(self, batch_id: str) -> list[dict[str, Any]]:
        batch = self.session.get(Batch, batch_id)
        if batch is None:
            raise KeyError(batch_id)
        maximum = self._maximum(batch)
        criteria = self._criteria(batch)
        submissions = list(
            self.session.scalars(
                select(Submission).where(Submission.batch_id == batch_id).order_by(Submission.sid, Submission.id)
            )
        )
        reviews = list(
            self.session.scalars(
                select(Review).where(Review.submission_id.in_([item.id for item in submissions]))
            )
        ) if submissions else []
        by_key = {(item.submission_id, item.criterion_id): item for item in reviews}
        markers = marker_names(self.session)
        rows = []
        for item in submissions:
            row: dict[str, Any] = {
                "sid": item.sid or "",
                "status": item.status,
                "ai_total": item.ai_total if item.ai_total is not None else "",
                "final_total": item.final_total if item.final_total is not None else "",
                "maximum": maximum,
                "band": item.final_level or "",
                "marker": markers.get(item.confirmed_by or "", ""),
            }
            for criterion in criteria:
                review = by_key.get((item.id, criterion.id))
                row[criterion.name] = review.score if review and review.score is not None else ""
            rows.append(row)
        return rows

    # ---------------------------------------------------------------- report
    def submission_report(self, submission_id: str, audience: str) -> dict[str, Any]:
        submission = self.session.get(Submission, submission_id)
        if submission is None:
            raise KeyError(submission_id)
        batch = self.session.get(Batch, submission.batch_id)
        if batch is None:
            raise KeyError(submission.batch_id)
        if submission.status != SubmissionStatus.CONFIRMED.value:
            raise RuntimeError("report_not_ready")
        maximum = self._maximum(batch)
        markers = marker_names(self.session)
        stored_file = self.session.get(File, submission.file_id) if submission.file_id else None
        reviews = {
            item.criterion_id: item
            for item in self.session.scalars(select(Review).where(Review.submission_id == submission.id))
        }
        results = {
            item.criterion_id: item
            for item in self.session.scalars(select(AIResult).where(AIResult.submission_id == submission.id))
        }
        evidence = list(
            self.session.scalars(
                select(Evidence).where(Evidence.ai_result_id.in_([item.id for item in results.values()]))
            )
        ) if results else []
        evidence_by_result: dict[str, list[Evidence]] = {}
        for item in evidence:
            evidence_by_result.setdefault(item.ai_result_id, []).append(item)
        criteria = []
        for criterion in self._criteria(batch):
            review = reviews.get(criterion.id)
            result = results.get(criterion.id)
            score = float(review.score) if review and review.score is not None else 0.0
            # The criterion's own levels (HD…FL, Full/Partial/No credit, …), not the grade bands.
            own_levels = json.loads(criterion.levels_json or "[]")
            level = levels.level_for(own_levels, score) or {}
            position, count = levels.rank(own_levels, level or None)
            descriptor = str(level.get("description") or "")
            criteria.append(
                {
                    "criterion_id": criterion.id,
                    "name": criterion.name,
                    "score": score,
                    "max_score": criterion.weight,
                    "band": str(level.get("label") or ""),
                    "band_rank": position,
                    "band_count": count,
                    "descriptor": descriptor,
                    "comment": review.comment if review else "",
                    "ai_score": result.score if result else None,
                    "confidence": result.confidence if result else None,
                    "internal_rationale": result.rationale if result else None,
                    "evidence": [
                        {"page": item.page, "paragraph": item.para, "quote": item.quote}
                        for item in sorted(
                            evidence_by_result.get(result.id, []) if result else [],
                            key=lambda row: (row.page or 0, row.char_start),
                        )
                    ],
                }
            )
        final_total = float(submission.final_total or 0)
        ai_total = float(submission.ai_total) if submission.ai_total is not None else None
        band = level_for_score(final_total, maximum)
        payload = {
            "submission": {
                "id": submission.id,
                "sid": submission.sid,
                "filename": stored_file.original_name if stored_file else submission.id,
            },
            "batch": {"id": batch.id, "name": batch.name, "unit": batch.unit, "is_sample": bool(batch.is_sample)},
            "status": submission.status,
            "locked": batch.status == BatchStatus.FINALISED.value,
            "audience": audience,
            "final_total": final_total,
            "maximum": maximum,
            "band": band.value,
            "band_name": BAND_NAMES[Level(band.value)],
            "ai_total": ai_total,
            "adjustment": round(final_total - ai_total, 2) if ai_total is not None else None,
            "confirmed_at": iso_utc(submission.confirmed_at),
            "finalised_at": iso_utc(batch.finalised_at),
            "marker": {
                "id": submission.confirmed_by,
                "name": markers.get(submission.confirmed_by or "", submission.confirmed_by),
            }
            if submission.confirmed_by
            else None,
            "feedback": json.loads(submission.feedback_json) if submission.feedback_json else None,
            "criteria": criteria,
        }
        return project_for_audience(payload, audience)

    # --------------------------------------------------------------- helpers
    def _criteria(self, batch: Batch) -> list[RubricCriterion]:
        return list(
            self.session.scalars(
                select(RubricCriterion)
                .where(
                    RubricCriterion.rubric_id == batch.rubric_library_id,
                    RubricCriterion.rubric_version == batch.rubric_version,
                )
                .order_by(RubricCriterion.position)
            )
        )

    def _maximum(self, batch: Batch) -> float:
        return float(sum(float(item.weight) for item in self._criteria(batch)))

    def _files(self, submissions: list[Submission]) -> dict[str, File]:
        ids = [item.file_id for item in submissions if item.file_id]
        if not ids:
            return {}
        return {item.id: item for item in self.session.scalars(select(File).where(File.id.in_(ids)))}
