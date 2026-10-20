from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.service import AnalyticsUseCases
from app.api.common import translate_error
from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.job import Job
from app.db.models.submission import File, Submission
from app.deps import get_current_user, get_db, get_settings
from app.jobs.queue import JobQueue
from app.services.review_service import ReviewUseCases
from app.services.settings_service import load_ai_settings
from app.services.submission_service import marker_names, submission_row

router = APIRouter(tags=["submissions"])


@router.patch("/batches/{batch_id}/submissions/{submission_id}")
def patch_submission(
    batch_id: str, submission_id: str, payload: dict[str, Any], db: Session = Depends(get_db)
) -> dict:
    try:
        with db.begin():
            item = db.get(Submission, submission_id)
            if item is None or item.batch_id != batch_id:
                raise KeyError(submission_id)
            if int(payload["version"]) != item.version:
                raise RuntimeError("version_conflict")
            if "student_id" in payload:
                item.sid = payload["student_id"]
            if payload.get("excluded"):
                item.status = "excluded"
                item.excluded_reason = payload.get("excluded_reason") or "Excluded by tutor"
            item.version += 1
            item.updated_at = datetime.now(timezone.utc)
            stored_file = db.get(File, item.file_id) if item.file_id else None
            return {"submission": submission_row(item, stored_file, marker_names(db))}
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/submissions/{submission_id}/retry", status_code=202)
def retry_submission(
    submission_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        with db.begin():
            load_ai_settings(db, settings)
            item = db.get(Submission, submission_id)
            if item is None:
                raise KeyError(submission_id)
            if int(payload["version"]) != item.version:
                raise RuntimeError("version_conflict")
            if item.status != "failed":
                raise RuntimeError("invalid_transition")
            item.status = "queued"
            item.error_reason = None
            item.version += 1
            batch = db.get(Batch, item.batch_id)
            if batch is None:
                raise KeyError(item.batch_id)
            if batch.status == "failed_all":
                batch.status = "processing"
                batch.version += 1
            item.ai_summary = "Queued to retry remaining criteria"
            batch.status = "processing"
            batch.model_provider = settings.llm
            batch.model_name = settings.ai_model
            batch.prompt_version = "criterion-grade-coverage-v3"
            job = _enqueue_grade(db, item, batch, force=False)
            return {
                "submission_id": item.id,
                "batch_id": batch.id,
                "job_id": job.id,
                "status": item.status,
                "version": item.version,
            }
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/submissions/{submission_id}/review")
def get_review(
    submission_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return ReviewUseCases(db).open(submission_id, user["id"])
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/submissions/{submission_id}/file")
def get_file(submission_id: str, db: Session = Depends(get_db)) -> FileResponse:
    item = db.get(Submission, submission_id)
    stored = db.get(File, item.file_id) if item and item.file_id else None
    if item is None or stored is None or not Path(stored.path).exists():
        raise translate_error(KeyError(submission_id))
    return FileResponse(
        stored.path,
        media_type=stored.mime,
        filename=stored.original_name,
        content_disposition_type="inline",
        headers={"ETag": f'"doc-v{item.document_version}"'},
    )


@router.post("/submissions/{submission_id}/regrade", status_code=202)
def regrade_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Re-run retrieval and grading with the currently configured provider."""

    try:
        with db.begin():
            load_ai_settings(db, settings)
            item = db.get(Submission, submission_id)
            if item is None:
                raise KeyError(submission_id)
            batch = db.get(Batch, item.batch_id)
            if batch is None:
                raise KeyError(item.batch_id)
            if batch.status == "finalised" or item.status == "confirmed":
                raise PermissionError("submission_locked")
            queued = db.scalar(
                select(Job)
                .where(
                    Job.submission_id == submission_id,
                    Job.kind == "grade",
                    Job.status.in_(["queued", "running"]),
                )
            )
            if queued is not None:
                return {
                    "submission_id": item.id,
                    "batch_id": batch.id,
                    "job_id": queued.id,
                    "status": item.status,
                    "version": item.version,
                }
            item.status = "queued"
            item.error_reason = None
            item.ai_summary = "Queued to re-run retrieval and AI grading"
            item.version += 1
            batch.status = "processing"
            batch.model_provider = settings.llm
            batch.model_name = settings.ai_model
            batch.prompt_version = "criterion-grade-coverage-v3"
            batch.version += 1
            job = _enqueue_grade(db, item, batch, force=True)
            return {
                "submission_id": item.id,
                "batch_id": batch.id,
                "job_id": job.id,
                "status": item.status,
                "version": item.version,
            }
    except Exception as exc:
        raise translate_error(exc) from exc


def _enqueue_grade(db: Session, item: Submission, batch: Batch, *, force: bool) -> Job:
    return JobQueue(db).enqueue(
        "grade",
        {
            "batch_id": batch.id,
            "submission_id": item.id,
            "rubric_id": batch.rubric_library_id,
            "rubric_version": batch.rubric_version,
            "force": force,
        },
    )


@router.patch("/submissions/{submission_id}/criteria/{criterion_id}")
def save_criterion(
    submission_id: str, criterion_id: str, payload: dict[str, Any], db: Session = Depends(get_db)
) -> dict:
    try:
        with db.begin():
            return ReviewUseCases(db).save_criterion(
                submission_id, criterion_id, payload
            )
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/submissions/{submission_id}/confirm")
def confirm_submission(
    submission_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return ReviewUseCases(db).confirm(
                submission_id, user["id"], int(payload["version"])
            )
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/submissions/{submission_id}/claim")
def claim_submission(
    submission_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            item = db.get(Submission, submission_id)
            if item is None:
                raise KeyError(submission_id)
            now = datetime.now(timezone.utc)
            if (
                item.claimed_by not in {None, user["id"]}
                and item.claimed_until
                and item.claimed_until > now
            ):
                raise RuntimeError("claim_conflict")
            item.claimed_by = user["id"]
            item.claimed_until = now + timedelta(seconds=int(payload.get("ttl_seconds", 300)))
            item.version += 1
            return {
                "submission_id": item.id,
                "claimed_by": {"id": user["id"], "name": user["name"]},
                "claimed_until": item.claimed_until.isoformat(),
                "version": item.version,
            }
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/batches/{batch_id}/results")
def results(batch_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return AnalyticsUseCases(db).batch_results(batch_id)
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/batches/{batch_id}/export.csv")
def export_csv(batch_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    try:
        rows = AnalyticsUseCases(db).csv_rows(batch_id)
    except Exception as exc:
        raise translate_error(exc) from exc
    output = io.StringIO()
    fieldnames = list(rows[0]) if rows else ["sid", "status", "ai_total", "final_total", "maximum", "band", "marker"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{batch_id}.csv"'},
    )


@router.get("/submissions/{submission_id}/report")
def report(
    submission_id: str,
    audience: str = Query("internal", pattern="^(internal|student)$"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return AnalyticsUseCases(db).submission_report(submission_id, audience)
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/submissions/{submission_id}/report.pdf")
def report_pdf(submission_id: str) -> None:
    del submission_id
    raise HTTPException(
        501,
        {
            "error": {
                "code": "feature_not_enabled",
                "message": "Server-rendered report PDFs are post-MVP; print the report page instead",
                "details": None,
            }
        },
    )
