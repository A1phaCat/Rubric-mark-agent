"""Load the sample rubrics and batches into the database through the real services.

Usage: ``python -m app.sample.seed`` (from ``backend/``). The API server also runs it on
every start (``MARKER_RESET_SAMPLES_ON_START``, default on) and Home has a "Reset samples"
button (``POST /api/v1/samples/reset``), so the samples can be marked again in every demo.
Re-running removes and recreates the sample batches and sample rubrics, and pins the three
samples to Home again; the tutor's own batches, rubrics and AI settings are kept (their
batches stay in the list, unpinned).

What is real: the submission files (PDF/DOCX), their storage and text extraction, the
evidence offsets (located in the extracted text), every tutor edit and confirmation
(``ReviewUseCases``), batch completion and finalisation (``BatchUseCases``) and the
audit trail. What is replayed: the AI grading step, from the results recorded in
``manifest.py``, so samples load offline and identically on every machine.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import Base
from app.db.models.audit import AuditLog
from app.db.models.batch import Batch
from app.db.models.core import AppSetting, Term, User
from app.db.models.job import Job
from app.db.models.llm import LLMCall
from app.db.models.review import Review
from app.db.models.rubric import Rubric, RubricCriterion
from app.db.models.submission import AIResult, Evidence, File, Submission
from app.db.session import SessionLocal, engine
from app.domain import levels
from app.domain.bands import level_for_score
from app.domain.ids import new_id
from app.domain.states import BatchStatus, SubmissionStatus
from app.retrieval import locate_quote
from app.rubric.parser import extract_rubric_file, parse_rubric_text
from app.sample import manifest
from app.services.batch_service import BatchUseCases
from app.services.review_service import ReviewUseCases
from app.services.rubric_service import RubricUseCases
from app.services.submission_service import apply_extraction, store_upload

FILES = Path(__file__).resolve().parent / "files"
SAMPLE_PROVIDER = "sample"
SAMPLE_MODEL = "recorded-sample"
PROMPT_VERSION = "criterion-grade-coverage-v3"
CONFIDENCE_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


class SampleDataError(RuntimeError):
    pass


def seed() -> dict[str, int]:
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        _ensure_people(session)
        _remove_previous_samples(session)
    with SessionLocal.begin() as session:
        criteria_by_rubric = _create_rubrics(session)
    counts = {"rubrics": len(criteria_by_rubric), "batches": 0, "submissions": 0}
    for spec in manifest.BATCHES:
        with SessionLocal.begin() as session:
            counts["submissions"] += _create_batch(session, spec)
            counts["batches"] += 1
    with SessionLocal.begin() as session:
        # Show the samples on Home in manifest order (the first one on top).
        now = datetime.now(timezone.utc)
        for index, spec in enumerate(manifest.BATCHES):
            batch = session.get(Batch, spec["id"])
            if batch is not None and batch.pinned:
                batch.pinned_at = now - timedelta(seconds=index)
    return counts


# ----------------------------------------------------------------------------- setup
def _ensure_people(session: Session) -> None:
    for person in (manifest.LOCAL_USER, manifest.OTHER_MARKER):
        if session.get(User, person["id"]) is None:
            session.add(User(role="tutor", **person))
    if session.get(Term, manifest.TERM["id"]) is None:
        session.add(Term(**manifest.TERM))
    for key, value in (("ai.provider", "university"), ("canvas.enabled", "false")):
        if session.get(AppSetting, key) is None:
            session.add(AppSetting(key=key, value_encrypted=value))
    session.flush()


def _remove_previous_samples(session: Session) -> None:
    sample_batches = list(session.scalars(select(Batch).where(Batch.is_sample.is_(True))))
    for batch in sample_batches:
        _delete_batch_rows(session, batch)
    session.flush()
    in_use = set(
        session.scalars(select(Batch.rubric_library_id).where(Batch.rubric_library_id.is_not(None)))
    )
    sample_ids = {item["id"] for item in load_rubric_files()}
    for rubric in list(session.scalars(select(Rubric))):
        if rubric.id in in_use:
            continue  # kept: one of the tutor's own batches marks against it
        if rubric.is_sample or rubric.id in sample_ids:
            session.execute(delete(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id))
            session.delete(rubric)


def _delete_batch_rows(session: Session, batch: Batch) -> None:
    submission_ids = list(session.scalars(select(Submission.id).where(Submission.batch_id == batch.id)))
    if submission_ids:
        result_ids = list(
            session.scalars(select(AIResult.id).where(AIResult.submission_id.in_(submission_ids)))
        )
        if result_ids:
            session.execute(delete(Evidence).where(Evidence.ai_result_id.in_(result_ids)))
        session.execute(delete(AIResult).where(AIResult.submission_id.in_(submission_ids)))
        session.execute(delete(Review).where(Review.submission_id.in_(submission_ids)))
        session.execute(delete(LLMCall).where(LLMCall.submission_id.in_(submission_ids)))
        session.execute(delete(AuditLog).where(AuditLog.entity_id.in_(submission_ids)))
    session.execute(delete(AuditLog).where(AuditLog.entity_id == batch.id))
    session.execute(delete(Job).where(Job.batch_id == batch.id))
    session.execute(delete(Submission).where(Submission.batch_id == batch.id))
    for stored in session.scalars(select(File).where(File.batch_id == batch.id)):
        path = Path(stored.path)
        if settings.runtime_paths()["files"] in path.parents and path.is_file():
            path.unlink()
    session.execute(delete(File).where(File.batch_id == batch.id))
    session.delete(batch)


RUBRIC_FILES = Path(__file__).resolve().parent / "rubrics"
RUBRIC_SUFFIXES = {".json", ".md", ".csv", ".tsv", ".txt", ".docx", ".pdf"}


def load_rubric_files(folder: Path = RUBRIC_FILES) -> list[dict[str, Any]]:
    """Parse every rubric file in ``app/sample/rubrics`` with the local (non-AI) parser.

    The rubric id is ``rub_<file name>`` (``shortanswer.json`` → ``rub_shortanswer``). JSON
    files may also set ``source``, ``pinned`` and ``age_days``; Canvas exports are loaded as-is
    (unpinned). A file the parser cannot read exactly (missing points or labels, some levels
    described and others not, totals that disagree) stops the seed with the parser's
    warnings. Levels with labels and points only are accepted.
    """

    specs = []
    for path in sorted(folder.iterdir()):
        if (
            path.suffix.lower() not in RUBRIC_SUFFIXES
            or path.name.startswith(("_", "."))
            or path.stem.lower() == "readme"
        ):
            continue
        text = extract_rubric_file(path.name, path.read_bytes())
        try:
            parsed = parse_rubric_text(text, path.name)
        except ValueError as exc:
            raise SampleDataError(f"rubrics/{path.name}: {exc}") from exc
        # Label-only levels are valid ("info"); anything that could make a mark wrong stops the seed.
        problems = [
            item.get("message", str(item)) if isinstance(item, dict) else str(item)
            for item in parsed.get("warnings", [])
            if not (isinstance(item, dict) and item.get("severity") == "info")
        ]
        if problems:
            raise SampleDataError(f"rubrics/{path.name}: " + "; ".join(problems))
        extra = json.loads(text) if path.suffix.lower() == ".json" else {}
        canvas = isinstance(extra, dict) and isinstance(extra.get("rubric"), list)
        specs.append(
            {
                "id": "rub_" + re.sub(r"[^a-z0-9]+", "", path.stem.lower()),
                "title": parsed["title"],
                "source": (None if canvas else extra.get("source")) or parsed.get("source") or f"Preloaded · {path.name}",
                "pinned": bool(extra.get("pinned", not canvas)) if not canvas else False,
                "age_days": float(extra.get("age_days", 2 if canvas else 0)),
                "criteria": [
                    {
                        "name": criterion["name"],
                        "weight": criterion["weight"],
                        "description": criterion.get("description", ""),
                        "score_mapping": criterion.get("score_mapping", "explicit"),
                        "levels": criterion["levels"],
                    }
                    for criterion in parsed["criteria"]
                ],
            }
        )
    return specs


def _create_rubrics(session: Session) -> dict[str, list[RubricCriterion]]:
    service = RubricUseCases(session)
    now = datetime.now(timezone.utc)
    created: dict[str, list[RubricCriterion]] = {}
    for spec in load_rubric_files():
        if session.get(Rubric, spec["id"]) is not None:
            # Still used by a tutor's batch: reuse the stored version 1 the samples mark against.
            created[spec["id"]] = _criteria_v1(session, spec["id"])
            continue
        service.create(
            {"title": spec["title"], "source": spec["source"], "criteria": spec["criteria"]},
            manifest.LOCAL_USER["id"],
            rubric_id=spec["id"],
            is_sample=True,
        )
        rubric = session.get(Rubric, spec["id"])
        assert rubric is not None
        rubric.created_at = rubric.updated_at = now - timedelta(days=spec["age_days"], hours=1)
        rubric.pinned = spec.get("pinned", True)
        created[spec["id"]] = _criteria_v1(session, spec["id"])
    return created


def _criteria_v1(session: Session, rubric_id: str) -> list[RubricCriterion]:
    return list(
        session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_id == rubric_id, RubricCriterion.rubric_version == 1)
            .order_by(RubricCriterion.position)
        )
    )


# ----------------------------------------------------------------------------- batches
def _create_batch(session: Session, spec: dict[str, Any]) -> int:
    now = datetime.now(timezone.utc)
    batches = BatchUseCases(session)
    reviews = ReviewUseCases(session)
    actor = manifest.LOCAL_USER["id"]
    batches.create(
        {
            "name": spec["name"],
            "unit": spec["unit"],
            "term_id": manifest.TERM["id"],
            "due_at": (now + timedelta(days=spec["due_in_days"])).replace(
                hour=12, minute=0, second=0, microsecond=0
            ).isoformat(),
            "rubric_id": spec["rubric_id"],
            "rubric_version": 1,
        },
        actor,
        batch_id=spec["id"],
        is_sample=True,
    )
    batch = session.get(Batch, spec["id"])
    assert batch is not None
    criteria = batches.snapshot_rubric(batch)

    # Upload and extract each file exactly as the upload API and worker do.
    stored: list[tuple[dict[str, Any], Submission]] = []
    for item in spec["submissions"]:
        path = FILES / item["file"]
        entry = store_upload(session, settings, batch, item["file"], path.read_bytes())
        session.flush()
        submission = session.get(Submission, entry["submission_id"])
        assert submission is not None
        stored_file = session.get(File, entry["id"])
        assert stored_file is not None
        if submission.sid != item["sid"]:
            raise SampleDataError(f"{item['file']}: SID detected as {submission.sid}")
        apply_extraction(session, submission, stored_file)
        stored.append((item, submission))

    batch.status = BatchStatus.PROCESSING.value
    batch.started_at = now - timedelta(days=spec["started_days_ago"])
    batch.model_provider = SAMPLE_PROVIDER
    batch.model_name = SAMPLE_MODEL
    batch.prompt_version = PROMPT_VERSION
    batch.version += 1

    for item, submission in stored:
        if item["outcome"] == "needs_manual":
            if submission.status != SubmissionStatus.NEEDS_OCR.value:
                raise SampleDataError(f"{item['file']} was expected to have no text layer")
            continue
        _record_ai_results(session, batch, submission, criteria, item)
    batches.refresh_status(batch.id)

    # Tutor decisions go through the same use cases as the review page.
    confirmed_at = now - timedelta(days=max(spec["started_days_ago"] - 1, 0))
    for index, (item, submission) in enumerate(stored):
        if item["outcome"] == "in_review":
            reviews.open(submission.id, actor)
        elif item["outcome"] == "confirmed":
            marker = item.get("marker", actor)
            reviews.open(submission.id, marker)
            current = {
                review.criterion_id: review
                for review in session.scalars(select(Review).where(Review.submission_id == submission.id))
            }
            for criterion, (score, comment) in zip(criteria, item["review"]):
                review = current[criterion.id]
                reviews.save_criterion(
                    submission.id,
                    criterion.id,
                    {"score": float(score), "comment": comment, "version": review.version},
                )
            submission.marker_id = marker
            submission.feedback_json = json.dumps(item["feedback"], ensure_ascii=False)
            session.flush()
            reviews.confirm(submission.id, marker, submission.version)
            submission.confirmed_at = confirmed_at + timedelta(minutes=7 * index)

    if spec["state"] == "finalised":
        session.flush()
        batches.finalise(batch.id, actor, batch.version)
        batch.finalised_at = confirmed_at + timedelta(days=1)

    session.flush()
    expected = spec["state"]
    if batch.status != expected:
        raise SampleDataError(f"{batch.id} ended as {batch.status}, expected {expected}")
    if batch.completed_at is not None:
        batch.completed_at = confirmed_at + timedelta(hours=2)
    batch.created_at = now - timedelta(days=spec["created_days_ago"])
    return len(stored)


def _record_ai_results(
    session: Session,
    batch: Batch,
    submission: Submission,
    criteria: list[RubricCriterion],
    item: dict[str, Any],
) -> None:
    """Persist recorded AI results with evidence located in the extracted text."""

    if len(item["ai"]) != len(criteria):
        raise SampleDataError(f"{item['file']}: {len(item['ai'])} AI results for {len(criteria)} criteria")
    document = json.loads(submission.document_json or "{}")
    now = datetime.now(timezone.utc)
    total = 0.0
    confidences: list[str] = []
    evidence_count = 0
    for criterion, result in zip(criteria, item["ai"]):
        score = float(result["score"])
        if not 0 <= score <= criterion.weight:
            raise SampleDataError(f"{item['file']}: score {score} outside 0–{criterion.weight}")
        level = str((levels.level_for(json.loads(criterion.levels_json or "[]"), score) or {}).get("label") or "")
        ai_result = AIResult(
            id=new_id("air"),
            submission_id=submission.id,
            criterion_id=criterion.id,
            level=level,
            score=score,
            rationale=result["rationale"],
            minor_json=json.dumps({"grading_mode": "recorded_sample"}),
            coverage_json="[]",
            sufficiency=result["sufficiency"],
            confidence=result["confidence"],
            self_confidence=None,
            provider=SAMPLE_PROVIDER,
            model=SAMPLE_MODEL,
            prompt_version=PROMPT_VERSION,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            created_at=now,
        )
        session.add(ai_result)
        session.flush()
        for quote, role in result["evidence"]:
            location = locate_quote(document, quote)
            if location is None:
                raise SampleDataError(f"{item['file']}: quote not found in extracted text: {quote!r}")
            session.add(
                Evidence(
                    id=new_id("evd"),
                    ai_result_id=ai_result.id,
                    role=role,
                    quote=quote,
                    page=location.page,
                    para=location.paragraph,
                    char_start=location.start_offset,
                    char_end=location.end_offset,
                    document_version=submission.document_version,
                    valid=True,
                )
            )
            evidence_count += 1
        session.add(
            Review(
                id=new_id("rev"),
                submission_id=submission.id,
                criterion_id=criterion.id,
                score=score,
                comment="",
                status="ai_suggested",
                updated_by=batch.created_by,
                updated_at=now,
                version=1,
            )
        )
        total += score
        confidences.append(result["confidence"])
    maximum = float(sum(criterion.weight for criterion in criteria))
    submission.ai_total = round(total, 2)
    submission.ai_level = level_for_score(total, maximum).value
    submission.min_confidence = min(confidences, key=lambda value: CONFIDENCE_ORDER[value])
    submission.ai_summary = f"{evidence_count} verified evidence passage(s) retrieved"
    submission.status = SubmissionStatus.AI_DONE.value
    submission.version += 1
    submission.updated_at = now
    session.flush()


def main() -> None:
    counts = seed()
    print(
        "Loaded sample data: "
        f"{counts['rubrics']} rubrics, {counts['batches']} batches, {counts['submissions']} submissions"
    )


if __name__ == "__main__":
    main()
