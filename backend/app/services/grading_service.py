from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.review import Review
from app.db.models.submission import AIResult, Evidence, Submission
from app.domain.ids import new_id
from app.grading import grade_criterion
from app.llm.protocol import FatalProviderError, ProviderError
from app.retrieval import FullDocument, full_document, retrieve_passages


class BatchCancelled(RuntimeError):
    pass


class LeaseLost(RuntimeError):
    """The worker no longer owns this job; another slot may be grading it."""


class DocumentTooLong(RuntimeError):
    """The submission does not fit the model's context window; a tutor marks it by hand."""

    final = True

    def __init__(self, estimated_tokens: int | None, limit: int | None) -> None:
        if estimated_tokens and limit:
            message = (
                f"Too long for the AI model to read whole (about {estimated_tokens:,} tokens; "
                f"the model reads up to {limit:,}). Mark by hand."
            )
        else:
            message = "Too long for the AI model to read whole. Mark by hand."
        super().__init__(message)
        self.estimated_tokens = estimated_tokens
        self.limit = limit


# Room left in the context window for the rubric, instructions and the model's answer.
_PROMPT_RESERVE_TOKENS = 12_000


class CriterionFailed(RuntimeError):
    """A criterion could not be graded. ``final``: running the job again will not help."""

    def __init__(self, message: str, *, final: bool) -> None:
        super().__init__(message)
        self.final = final


# Retries happen in one place per kind of failure:
#   provider (429 / 5xx / timeout) → the LLM client, honouring Retry-After
#   invalid or unverifiable model output → here, once more
#   worker crash / lost lease → the job queue
_OUTPUT_ATTEMPTS = 2


async def _grade_with_retry(
    settings: Settings,
    criterion: dict[str, Any],
    passages: list[Any],
    submission_id: str,
    position: int,
    *,
    full: FullDocument | None = None,
    after_gate: Callable[[], None] | None = None,
) -> dict[str, Any]:
    criterion_id = str(criterion["id"])
    name = criterion.get("name", criterion_id)
    for attempt in range(1, _OUTPUT_ATTEMPTS + 1):
        try:
            return await grade_criterion(
                settings,
                criterion,
                passages,
                {"submission_id": submission_id, "criterion_id": criterion_id, "attempt": str(attempt)},
                full=full,
                after_gate=after_gate,
            )
        except FatalProviderError as exc:
            if exc.reason == "context_length":
                raise DocumentTooLong(full.estimated_tokens if full else None, None) from exc
            raise CriterionFailed(f"C{position} {name}: {exc}", final=True) from exc
        except (ProviderError, NotImplementedError) as exc:
            # The client already waited and retried; a wrong key or model will not fix itself.
            raise CriterionFailed(f"C{position} {name}: {exc}", final=True) from exc
        except ValueError as exc:  # model output that is not valid JSON or does not match the text
            if attempt == _OUTPUT_ATTEMPTS:
                detail = str(exc).strip() or type(exc).__name__
                raise CriterionFailed(
                    f"C{position} {name}: model output rejected after {attempt} attempts: {detail}",
                    final=True,
                ) from exc
    raise AssertionError("unreachable")


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
    still_owned: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Retrieve, grade, verify, and persist one submission's criterion evidence.

    ``still_owned`` is the job lease check from the worker: when it turns false another
    worker slot may have taken the job, so grading stops before writing anything more.
    """

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

    def persist(
        position: int,
        criterion: dict[str, Any],
        criterion_id: str,
        completed: AIResult | None,
        passages: list[Any],
        result: dict[str, Any],
    ) -> tuple[float, str, int]:
        """Write one criterion's result; called on the event-loop thread, one at a time."""

        maximum = float(criterion.get("weight") or 0)
        score = max(0.0, min(maximum, float(result.get("score", 0))))
        confidence = str(result.get("confidence", "low")).lower()
        if confidence not in {"high", "medium", "low", "none"}:
            confidence = "low"

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
                    "context": "full" if full else "retrieval",
                },
                ensure_ascii=False,
            ),
            coverage_json=json.dumps(result.get("coverage", []), ensure_ascii=False),
            sufficiency=str(result.get("sufficiency") or "unknown"),
            confidence=confidence,
            self_confidence=None,
            provider=settings.llm,
            model=str(result.get("model") or settings.ai_model),
            prompt_version="criterion-grade-fulltext-v1" if full else "criterion-grade-coverage-v3",
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
        added = 0
        evidence_ids_by_passage: dict[str, list[str]] = {}
        for raw in selected[: 12 if full else settings.evidence_top_k]:
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
            added += 1

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

        processed[0] += 1
        submission.ai_summary = f"{processed[0]}/{len(criteria)} criteria processed"
        submission.version += 1
        session.flush()
        if commit_progress:
            # Never hold SQLite's single-writer lock while the next provider call runs.
            session.commit()
        return score, confidence, added

    # 1. What the evidence step reads. Full: every paragraph of the submission, once for
    #    all criteria — never truncated; a submission that cannot fit goes to a tutor.
    #    Retrieval: the passages retrieved for each criterion (evaluation comparison only).
    full: FullDocument | None = None
    if settings.grading_context == "full":
        full = full_document(document)
        limit_tokens = int(settings.ai_context_tokens) - _PROMPT_RESERVE_TOKENS
        if full.estimated_tokens > limit_tokens:
            raise DocumentTooLong(full.estimated_tokens, limit_tokens)
    pending: list[tuple[int, dict[str, Any], str, AIResult | None, list[Any]]] = []
    for position, criterion in enumerate(criteria, 1):
        criterion_id = str(criterion["id"])
        completed = existing.get(criterion_id)
        if completed is not None and not force:
            total += float(completed.score)
            confidence_values.append(completed.confidence)
            evidence_count += evidence_counts.get(completed.id, 0)
            continue
        passages = (
            full.passages
            if full is not None
            else retrieve_passages(
                document,
                criterion,
                limit=settings.retrieval_candidate_limit,
                settings=settings,
                submission_id=submission.id,
                document_version=submission.document_version,
            )
        )
        pending.append((position, criterion, criterion_id, completed, passages))

    # 2. Model calls for those criteria run concurrently (criterion_concurrency per
    #    submission, and the provider gate caps calls across all worker slots).
    # 3. Each result is written and committed as soon as it arrives, in this thread.
    processed = [len(criteria) - len(pending)]
    limit = asyncio.Semaphore(max(1, int(settings.criterion_concurrency)))

    def check_still_running() -> None:
        if still_owned is not None and not still_owned():
            raise LeaseLost("job_lease_lost")
        _require_active_batch(session, batch)

    # In full mode the first criterion goes alone until its evidence call has returned:
    # the provider has then cached the submission text, and the others reuse it.
    warm = asyncio.Event()
    if full is None or len(pending) <= 1:
        warm.set()
    first = pending[0][0] if pending else None

    async def run(item: tuple[int, dict[str, Any], str, AIResult | None, list[Any]]) -> tuple[Any, dict[str, Any]]:
        position, criterion, criterion_id, _completed, passages = item
        if position != first:
            await warm.wait()
        async with limit:
            check_still_running()
            try:
                result = await _grade_with_retry(
                    settings, criterion, passages, submission.id, position,
                    full=full, after_gate=warm.set if position == first else None,
                )
            finally:
                warm.set()  # never leave the others waiting if the first one fails
            return item, result

    check_still_running()
    tasks = [asyncio.ensure_future(run(item)) for item in pending]
    failure: BaseException | None = None
    try:
        for next_done in asyncio.as_completed(tasks):
            try:
                item, result = await next_done
            except (BatchCancelled, LeaseLost, DocumentTooLong):
                raise
            except Exception as exc:  # keep the other criteria's results; fail afterwards
                failure = failure or exc
                continue
            check_still_running()
            position, criterion, criterion_id, completed, passages = item
            score, confidence, added = persist(position, criterion, criterion_id, completed, passages, result)
            total += score
            confidence_values.append(confidence)
            evidence_count += added
            if commit_progress:
                # Never hold SQLite's single-writer lock while provider calls run.
                session.commit()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if failure is not None:
        raise failure

    confidence_order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    submission.ai_total = round(total, 2)
    submission.min_confidence = (
        min(confidence_values, key=confidence_order.get) if confidence_values else "none"
    )
    submission.ai_summary = f"{evidence_count} verified evidence passage(s) found"
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
