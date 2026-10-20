from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import mock, translate_error
from app.api.settings import load_ai_settings
from app.config import PROJECT_ROOT, Settings
from app.db.models.batch import Batch
from app.db.models.job import Job
from app.db.models.submission import File, Submission
from app.deps import get_current_user, get_db, get_settings
from app.jobs.queue import JobQueue
from app.services.batch_service import BatchUseCases
from app.services.fixture_service import FixtureStore
from app.services.review_service import ReviewUseCases

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
            return {"submission": _row(item)}
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
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            payload = ReviewUseCases(db, FixtureStore(settings.fixtures_dir)).open(
                submission_id, user["id"]
            )
        if payload.get("_mock"):
            response.headers["X-Mock"] = "true"
        return payload
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/submissions/{submission_id}/file")
def get_file(
    submission_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    item = db.get(Submission, submission_id)
    if item is None:
        raise translate_error(KeyError(submission_id))
    stored = db.get(File, item.file_id) if item.file_id else None
    if stored is not None and Path(stored.path).exists():
        return FileResponse(
            stored.path,
            media_type=stored.mime,
            filename=stored.original_name,
            content_disposition_type="inline",
            headers={"ETag": f'"doc-v{item.document_version}"'},
        )

    fixture_path = settings.fixtures_dir / "reviews" / f"{submission_id}.json"
    if not fixture_path.exists():
        raise translate_error(KeyError(submission_id))
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    filename = Path(str(fixture.get("submission", {}).get("filename") or "")).name
    demo_path = PROJECT_ROOT / "output" / "pdf" / filename
    if not filename or not demo_path.exists():
        raise translate_error(KeyError(submission_id))
    return FileResponse(
        demo_path,
        media_type="application/pdf",
        filename=filename,
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
            return ReviewUseCases(db, FixtureStore(Path("fixtures/demo"))).save_criterion(
                submission_id, criterion_id, payload
            )
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/submissions/{submission_id}/confirm")
def confirm_submission(
    submission_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return ReviewUseCases(db, FixtureStore(settings.fixtures_dir)).confirm(
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
def results(
    batch_id: str,
    response: Response,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    store = FixtureStore(settings.fixtures_dir)
    path = store.root / "reports" / f"results-{batch_id}.json"
    if path.exists():
        return mock(response, json.loads(path.read_text(encoding="utf-8")))
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise translate_error(KeyError(batch_id))
    rows = list(db.scalars(select(Submission).where(Submission.batch_id == batch_id).limit(50)))
    finals = [float(item.final_total) for item in rows if item.final_total is not None]
    ais = [float(item.ai_total) for item in rows if item.ai_total is not None]
    return {
        "batch": BatchUseCases(db).serialize(batch),
        "locked": batch.status == "finalised",
        "released_at": batch.finalised_at.isoformat() if batch.finalised_at else None,
        "released_to": None,
        "summary": {
            "average_final": sum(finals) / len(finals) if finals else None,
            "average_ai": sum(ais) / len(ais) if ais else None,
            "adjusted_count": 0,
            "adjusted_percent": 0,
            "comments_count": len(finals),
            "marker_count": 1,
        },
        "distribution": [],
        "criteria": [],
        "submissions": {
            "items": [_row(item) for item in rows],
            "page": 1,
            "page_size": 50,
            "total": batch.total_count,
        },
    }


@router.get("/batches/{batch_id}/export.csv")
def export_csv(batch_id: str, settings: Settings = Depends(get_settings)) -> StreamingResponse:
    rows = [
        item
        for item in FixtureStore(settings.fixtures_dir).submissions()
        if item["batch_id"] == batch_id
    ]
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=["submission_id", "sid", "ai_total", "final_total", "status"]
    )
    writer.writeheader()
    for item in rows:
        writer.writerow(
            {
                "submission_id": item["id"],
                "sid": item["sid"],
                "ai_total": item["ai_total"],
                "final_total": item["final_total"],
                "status": item["status"],
            }
        )
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{batch_id}.csv"'},
    )


@router.get("/submissions/{submission_id}/report")
def report(
    submission_id: str,
    response: Response,
    audience: str = Query("internal", pattern="^(internal|student)$"),
    settings: Settings = Depends(get_settings),
) -> dict:
    store = FixtureStore(settings.fixtures_dir)
    path = store.root / "reports" / f"{submission_id}.json"
    if not path.exists():
        path = store.root / "reports" / "shared-sample.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["submission"]["id"] = submission_id
    payload["audience"] = audience
    if audience == "student":
        payload.pop("ai_total", None)
        payload.pop("adjustment", None)
        for criterion in payload.get("criteria", []):
            criterion.pop("ai_score", None)
            criterion.pop("confidence", None)
            criterion.pop("internal_rationale", None)
    return mock(response, payload)


@router.get("/submissions/{submission_id}/report.pdf")
def report_pdf(submission_id: str, audience: str = "internal") -> Response:
    text = f"AI-assisted marker report {submission_id} ({audience})"
    escaped = text.replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode() + stream + b"\nendstream endobj\n",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return Response(
        bytes(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{submission_id}.pdf"'},
    )


def _row(item: Submission) -> dict[str, Any]:
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "sid": item.sid,
        "filename": item.sid or item.id,
        "status": item.status,
        "ai_total": item.ai_total,
        "final_total": item.final_total,
        "confidence": item.min_confidence,
        "marker": None,
        "flags": json.loads(item.flags_json),
        "error": {"code": "processing_failed", "message": item.error_reason}
        if item.error_reason
        else None,
        "updated_at": item.updated_at.isoformat(),
        "version": item.version,
        "_mock": item.is_mock,
    }
