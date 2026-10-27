from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.review import Review
from app.db.models.submission import AIResult, Evidence, Submission
from app.domain.ids import new_id
from app.grading import grade_criterion
from app.retrieval import retrieve_passages


class BatchCancelled(RuntimeError):
    pass


def _require_active_batch(session: Session, batch: Batch) -> None:
    session.refresh(batch, attribute_names=["status"])
    if batch.status == "cancelled":
        raise BatchCancelled("batch_cancelled")


async def grade_submission(
    session: Session,
    settings: Settings,
    submission: Submission,
    batch: Batch,
    criteria: list[dict[str, Any]],
    *,
    force: bool = False,
    commit_progress: bool = False,
) -> dict[str, Any]:
    """Retrieve, grade, verify, and persist one submission's criterion evidence."""

    if not submission.document_json:
        raise ValueError("submission_not_extracted")
    document = json.loads(submission.document_json)

    previous_results = list(
        session.scalars(select(AIResult).where(AIResult.submission_id == submission.id))
    )
    previous_ids = [item.id for item in previous_results]

    existing = {item.criterion_id: item for item in previous_results}
    existing_evidence = (
        list(session.scalars(select(Evidence).where(Evidence.ai_result_id.in_(previous_ids))))
        if previous_ids
        else []
    )
    evidence_counts: dict[str, int] = {}
    for evidence in existing_evidence:
        evidence_counts[evidence.ai_result_id] = evidence_counts.get(evidence.ai_result_id, 0) + 1

    total = 0.0
    confidence_values: list[str] = []
    evidence_count = 0
    now = datetime.now(timezone.utc)

    for position, criterion in enumerate(criteria, 1):
        _require_active_batch(session, batch)
        criterion_id = str(criterion["id"])
        completed = existing.get(criterion_id)
        if completed is not None and not force:
            total += float(completed.score)
            confidence_values.append(completed.confidence)
            evidence_count += evidence_counts.get(completed.id, 0)
            continue
        passages = retrieve_passages(
            document,
            criterion,
            limit=settings.retrieval_candidate_limit,
            settings=settings,
            submission_id=submission.id,
            document_version=submission.document_version,
        )
        result: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                result = await grade_criterion(
                    settings,
                    criterion,
                    passages,
                    {
                        "submission_id": submission.id,
                        "criterion_id": criterion_id,
                        "attempt": str(attempt),
                    },
                )
                _require_active_batch(session, batch)
                break
            except BatchCancelled:
                raise
            except Exception as exc:  # provider and schema failures are retryable here
                last_error = exc
                if attempt < 3:
                    await asyncio.sleep(0.75 * (2 ** (attempt - 1)))
        if result is None:
            detail = str(last_error).strip() if last_error else "unknown grading error"
            detail = detail or type(last_error).__name__
            raise RuntimeError(
                f"C{position} {criterion.get('name', criterion_id)} failed after 3 attempts: {detail}"
            ) from last_error
        maximum = float(criterion.get("weight") or 0)
        score = max(0.0, min(maximum, float(result.get("score", 0))))
        confidence = str(result.get("confidence", "low")).lower()
        if confidence not in {"high", "medium", "low", "none"}:
            confidence = "low"
        confidence_values.append(confidence)
        total += score

        if force and completed is not None:
            session.execute(delete(Evidence).where(Evidence.ai_result_id == completed.id))
            session.execute(delete(AIResult).where(AIResult.id == completed.id))

        ai_result = AIResult(
            id=new_id("air"),
            submission_id=submission.id,
            criterion_id=criterion_id,
            level=str(result.get("level") or "suggested"),
            score=round(score, 2),
            rationale=str(result.get("rationale") or "No rationale returned."),
            minor_json=json.dumps(
                {
                    "grading_mode": result.get("grading_mode", criterion.get("grading_mode")),
                    "coverage_ratio": result.get("coverage_ratio", 0),
                    "missing_aspects": result.get("missing_aspects", []),
                },
                ensure_ascii=False,
            ),
            coverage_json=json.dumps(result.get("coverage", []), ensure_ascii=False),
            sufficiency=str(result.get("sufficiency") or "unknown"),
            confidence=confidence,
            self_confidence=None,
            provider=settings.llm,
            model=str(result.get("model") or settings.ai_model),
            prompt_version="criterion-grade-coverage-v3",
            input_tokens=int(result.get("input_tokens") or 0),
            output_tokens=int(result.get("output_tokens") or 0),
            latency_ms=int(result.get("latency_ms") or 0),
            created_at=now,
        )
        session.add(ai_result)
        session.flush()

        passage_by_id = {item.id: item for item in passages}
        selected = result.get("evidence") if isinstance(result.get("evidence"), list) else []
        persisted_quotes: set[str] = set()
        evidence_ids_by_passage: dict[str, list[str]] = {}
        for raw in selected[: settings.evidence_top_k]:
            if not isinstance(raw, dict):
                continue
            passage = passage_by_id.get(str(raw.get("passage_id", "")))
            if passage is None:
                continue
            quote = str(raw.get("quote") or "").strip()
            if not quote or quote not in passage.text:
                continue
            evidence_key = " ".join(quote.lower().split())
            if evidence_key in persisted_quotes:
                continue
            persisted_quotes.add(evidence_key)
            local_start = passage.text.index(quote)
            role = str(raw.get("role") or "supporting")
            if role not in {"primary", "supporting"}:
                role = "supporting"
            evidence_id = new_id("evd")
            session.add(
                Evidence(
                    id=evidence_id,
                    ai_result_id=ai_result.id,
                    role=role,
                    quote=quote,
                    page=passage.page,
                    para=passage.paragraph,
                    char_start=passage.start_offset + local_start,
                    char_end=passage.start_offset + local_start + len(quote),
                    document_version=submission.document_version,
                    valid=True,
                )
            )
            evidence_ids_by_passage.setdefault(passage.id, []).append(evidence_id)
            evidence_count += 1

        stored_coverage = []
        for coverage_item in result.get("coverage", []):
            if not isinstance(coverage_item, dict):
                continue
            row = dict(coverage_item)
            row["evidence_ids"] = [
                evidence_id
                for passage_id in coverage_item.get("evidence_ids", [])
                for evidence_id in evidence_ids_by_passage.get(str(passage_id), [])
            ]
            row["contradictory_evidence_ids"] = [
                evidence_id
                for passage_id in coverage_item.get("contradictory_evidence_ids", [])
                for evidence_id in evidence_ids_by_passage.get(str(passage_id), [])
            ]
            stored_coverage.append(row)
        ai_result.coverage_json = json.dumps(stored_coverage, ensure_ascii=False)

        review = session.scalar(
            select(Review).where(
                Review.submission_id == submission.id,
                Review.criterion_id == criterion_id,
            )
        )
        if review is None:
            session.add(
                Review(
                    id=new_id("rev"),
                    submission_id=submission.id,
                    criterion_id=criterion_id,
                    score=round(score, 2),
                    comment="",
                    status="ai_suggested",
                    updated_by=batch.created_by,
                    updated_at=now,
                    version=1,
                )
            )
        else:
            review.score = round(score, 2)
            review.status = "ai_suggested"
            review.updated_at = now
            review.version += 1

        submission.ai_summary = f"{position}/{len(criteria)} criteria processed"
        submission.version += 1
        session.flush()
        if commit_progress:
            # Never hold SQLite's single-writer lock while the next provider call runs.
            session.commit()

    confidence_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    submission.ai_total = round(total, 2)
    submission.min_confidence = (
        min(confidence_values, key=confidence_order.get) if confidence_values else "none"
    )
    submission.ai_summary = f"{evidence_count} verified evidence passage(s) retrieved"
    submission.error_reason = None
    submission.version += 1
    session.flush()
    return {
        "submission_id": submission.id,
        "provider": settings.llm,
        "model": settings.ai_model if settings.llm != "fake" else "fake-marker-v1",
        "ai_total": submission.ai_total,
        "confidence": submission.min_confidence,
        "evidence_count": evidence_count,
    }
