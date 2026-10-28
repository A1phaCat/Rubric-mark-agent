from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.api.common import translate_error
from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.submission import File, Submission
from app.db.session import SessionLocal
from app.deps import get_current_user, get_db, get_settings
from app.services.batch_service import PROCESSING_STATES, BatchUseCases
from app.services.review_service import MANUAL_STATES, READY_STATES, ReviewUseCases
from app.services.settings_service import load_ai_settings
from app.services.submission_service import marker_names, submission_row

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("")
def list_batches(
    active: bool | None = None,
    term: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return BatchUseCases(db).list(
        active=active, term=term, status=status, q=q, page=page, page_size=page_size
    )


@router.post("", status_code=201)
def create_batch(
    payload: dict[str, Any], db: Session = Depends(get_db), user: dict = Depends(get_current_user)
) -> dict:
    try:
        with db.begin():
            return BatchUseCases(db).create(payload, user["id"])
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        batch = db.get(Batch, batch_id)
        if batch is None:
            raise KeyError(batch_id)
        return {
            "batch": BatchUseCases(db).serialize(batch),
            "rubric_snapshot": json.loads(batch.rubric_snapshot_json)
            if batch.rubric_snapshot_json
            else None,
            "previous_batch": None,
            "next_batch": None,
        }
    except Exception as exc:
        raise translate_error(exc) from exc


SUBMISSION_FILTERS = {
    "ready": lambda item: item.status in READY_STATES,
    "low_confidence": lambda item: item.status in READY_STATES and item.min_confidence == "low",
    "needs_manual": lambda item: item.status in MANUAL_STATES,
    "processing": lambda item: item.status in PROCESSING_STATES,
    "confirmed": lambda item: item.status == "confirmed",
    "failed": lambda item: item.status == "failed",
}


@router.get("/{batch_id}/submissions")
def list_submissions(
    batch_id: str,
    filter: str = "all",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    try:
        if db.get(Batch, batch_id) is None:
            raise KeyError(batch_id)
        service = BatchUseCases(db)
        completed_rank = case((Submission.status == "confirmed", 1), else_=0)
        records = list(
            db.scalars(
                select(Submission)
                .where(Submission.batch_id == batch_id)
                .order_by(completed_rank, Submission.sid, Submission.id)
            )
        )
        adjusted = service.adjusted_submission_ids(batch_id)
        if filter == "adjusted":
            records = [item for item in records if item.id in adjusted]
        elif filter in SUBMISSION_FILTERS:
            records = [item for item in records if SUBMISSION_FILTERS[filter](item)]
        elif filter != "all":
            raise ValueError(f"Unknown submission filter: {filter}")
        files = {
            item.id: item
            for item in db.scalars(select(File).where(File.batch_id == batch_id))
        }
        markers = marker_names(db)
        start = (page - 1) * page_size
        return {
            "items": [
                submission_row(item, files.get(item.file_id or ""), markers, adjusted=item.id in adjusted)
                for item in records[start : start + page_size]
            ],
            "page": page,
            "page_size": page_size,
            "total": len(records),
            "filter_counts": service.counts(batch_id),
        }
    except Exception as exc:
        raise translate_error(exc) from exc


@router.put("/{batch_id}/pin")
def pin_batch(batch_id: str, payload: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    try:
        with db.begin():
            return BatchUseCases(db).set_pinned(batch_id, bool(payload.get("pinned", True)))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{batch_id}/start")
async def start_batch(
    batch_id: str,
    payload: dict[str, Any],
    sample: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        with db.begin():
            load_ai_settings(db, settings)
            return BatchUseCases(db).start(batch_id, payload, sample, settings)
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{batch_id}/finalise")
def finalise_batch(
    batch_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return BatchUseCases(db).finalise(batch_id, user["id"], int(payload["version"]))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{batch_id}/reopen")
def reopen_batch(
    batch_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return BatchUseCases(db).reopen(
                batch_id, user["id"], payload["reason"], int(payload["version"])
            )
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{batch_id}/pause")
def pause_batch(
    batch_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return BatchUseCases(db).pause(batch_id, user["id"], int(payload["version"]))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{batch_id}/resume")
def resume_batch(
    batch_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return BatchUseCases(db).resume(batch_id, user["id"], int(payload["version"]))
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/{batch_id}/cancel")
def cancel_batch(
    batch_id: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            return BatchUseCases(db).cancel(
                batch_id,
                user["id"],
                str(payload.get("reason") or "Batch terminated by user"),
                int(payload["version"]),
            )
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{batch_id}")
def delete_batch(
    batch_id: str,
    version: int = Query(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(get_current_user),
) -> dict:
    try:
        with db.begin():
            result = BatchUseCases(db).delete(batch_id, user["id"], version)
        files_root = settings.runtime_paths()["files"].resolve()
        removed_files = 0
        for raw_path in result.pop("file_paths", []):
            candidate = Path(raw_path).resolve()
            if files_root not in candidate.parents or not candidate.is_file():
                continue
            candidate.unlink()
            removed_files += 1
            parent = candidate.parent
            if parent != files_root and parent.parent == files_root and not any(parent.iterdir()):
                parent.rmdir()
        return {**result, "removed_files": removed_files}
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{batch_id}/queue/next")
def next_submission(batch_id: str, after: str | None = None, db: Session = Depends(get_db)) -> dict:
    try:
        if db.get(Batch, batch_id) is None:
            raise KeyError(batch_id)
        upcoming = ReviewUseCases(db).queue(batch_id, limit=1, after=after, exclude={after} if after else None)
        counts = BatchUseCases(db).counts(batch_id)
        return {
            "next_id": upcoming[0].id if upcoming else None,
            "next_sid": upcoming[0].sid if upcoming else None,
            "remaining": {
                "ready": counts["ready"],
                "needs_manual": counts["needs_manual"],
                "processing": counts["processing"],
                "failed": counts["failed"],
                "confirmed": counts["confirmed"],
                "total": counts["total"],
            },
        }
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{batch_id}/events")
async def events(batch_id: str, request: Request) -> StreamingResponse:
    """Progress events read from the database, so updates written by the separate
    worker process reach the browser (an in-memory bus cannot cross processes)."""

    def snapshot() -> tuple[int, dict[str, Any]] | None:
        with SessionLocal() as session:
            batch = session.get(Batch, batch_id)
            if batch is None:
                return None
            service = BatchUseCases(session)
            counts = service.counts(batch_id)
            queue = service.queue_wait(batch, counts)
            return batch.version, {
                "batch_id": batch_id,
                "status": batch.status,
                "counts": counts,
                "eta_seconds": service.estimate_eta(batch, counts, queue),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    async def stream():
        last_version: int | None = None
        idle = 0.0
        while not await request.is_disconnected():
            # The snapshot is a blocking SQLite read that can wait up to busy_timeout while
            # the worker writes; run it off the event loop so open progress pages never
            # stall every other request.
            current = await asyncio.to_thread(snapshot)
            if current is None:
                yield "event: error\ndata: {\"code\": \"not_found\"}\n\n"
                return
            version, data = current
            if version != last_version:
                last_version, idle = version, 0.0
                yield f"event: batch_progress\ndata: {json.dumps(data)}\n\n"
            elif idle >= 15:
                idle = 0.0
                yield ": heartbeat\n\n"
            await asyncio.sleep(2)
            idle += 2

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/{batch_id}/report-export")
def batch_report_export(batch_id: str) -> None:
    del batch_id
    from fastapi import HTTPException

    raise HTTPException(
        501,
        {
            "error": {
                "code": "feature_not_enabled",
                "message": "Batch PDF export is post-MVP",
                "details": None,
            }
        },
    )
