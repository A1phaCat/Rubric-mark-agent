from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import mock, translate_error
from app.api.settings import load_ai_settings
from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.submission import Submission
from app.deps import get_current_user, get_db, get_settings
from app.events.bus import event_bus
from app.services.batch_service import BatchUseCases
from app.services.fixture_service import FixtureStore

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("")
def list_batches(
    response: Response,
    active: bool | None = None,
    term: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    service = BatchUseCases(db)
    persisted = [service.serialize(item) for item in db.scalars(select(Batch).order_by(Batch.created_at.desc()))]
    persisted_ids = {item["id"] for item in persisted}
    items = persisted + [
        item for item in FixtureStore(settings.fixtures_dir).batches() if item["id"] not in persisted_ids
    ]
    if active:
        items = [item for item in items if item["status"] not in {"finalised", "cancelled"}]
    if term:
        items = [item for item in items if item["term"]["id"] == term]
    if status:
        items = [item for item in items if item["status"] == status]
    if q:
        lowered = q.lower()
        items = [
            item for item in items if lowered in f"{item['name']} {item.get('unit', '')}".lower()
        ]
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    start = (page - 1) * page_size
    return mock(
        response,
        {
            "items": items[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(items),
        },
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
def get_batch(
    batch_id: str,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    fixture = FixtureStore(settings.fixtures_dir).batch(batch_id)
    if fixture:
        return mock(
            response,
            {"batch": fixture, "rubric_snapshot": None, "previous_batch": None, "next_batch": None},
        )
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


@router.get("/{batch_id}/submissions")
def list_submissions(
    batch_id: str,
    response: Response,
    filter: str = "all",
    page: int = 1,
    page_size: int = 50,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    store = FixtureStore(settings.fixtures_dir)
    fixture_batch = store.batch(batch_id)
    if fixture_batch is None:
        records = list(
            db.scalars(
                select(Submission).where(Submission.batch_id == batch_id).order_by(Submission.id)
            )
        )
        if not records and db.get(Batch, batch_id) is None:
            raise translate_error(KeyError(batch_id))
        rows = [
            {
                "id": item.id,
                "batch_id": item.batch_id,
                "sid": item.sid,
                "filename": item.sid or item.id,
                "status": item.status,
                "ai_total": item.ai_total,
                "final_total": item.final_total,
                "confidence": item.min_confidence,
                "progress": item.ai_summary,
                "marker": None,
                "flags": json.loads(item.flags_json),
                "error": {
                    "code": "processing_failed",
                    "message": item.error_reason or "AI grading failed without an error message",
                }
                if item.status == "failed"
                else None,
                "updated_at": item.updated_at.isoformat(),
                "version": item.version,
                "_mock": item.is_mock,
            }
            for item in records
        ]
        counts = BatchUseCases(db).counts(batch_id)
        start = (page - 1) * page_size
        return {
            "items": rows[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(rows),
            "filter_counts": counts,
        }
    rows = [item for item in store.submissions() if item["batch_id"] == batch_id]
    if filter != "all":
        if filter == "ready":
            rows = [item for item in rows if item["status"] in {"ai_done", "in_review"}]
        elif filter == "low_confidence":
            rows = [item for item in rows if item.get("confidence") == "low"]
        elif filter == "needs_manual":
            rows = [item for item in rows if "needs_manual" in item.get("flags", [])]
        elif filter == "processing":
            rows = [
                item
                for item in rows
                if item["status"] in {"uploaded", "extracting", "queued", "marking"}
            ]
        else:
            rows = [
                item for item in rows if item["status"] == filter or filter in item.get("flags", [])
            ]
    batch = fixture_batch
    start = (page - 1) * page_size
    return mock(
        response,
        {
            "items": rows[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(rows),
            "filter_counts": batch["counts"] if batch else {},
        },
    )


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
def next_submission(
    batch_id: str,
    response: Response,
    after: str | None = None,
    settings: Settings = Depends(get_settings),
) -> dict:
    rows = [
        item
        for item in FixtureStore(settings.fixtures_dir).submissions()
        if item["batch_id"] == batch_id and item["status"] in {"ai_done", "in_review"}
    ]
    index = next((i for i, item in enumerate(rows) if item["id"] == after), -1)
    next_id = rows[index + 1]["id"] if index + 1 < len(rows) else None
    batch = FixtureStore(settings.fixtures_dir).batch(batch_id)
    counts = batch["counts"] if batch else {}
    return mock(
        response,
        {
            "next_id": next_id,
            "remaining": {
                "ready": counts.get("ready", 0),
                "processing": counts.get("processing", 0),
                "failed": counts.get("failed", 0),
            },
        },
    )


@router.get("/{batch_id}/events")
async def events(
    batch_id: str, request: Request, settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    fixture_batch = FixtureStore(settings.fixtures_dir).batch(batch_id)

    async def stream():
        if fixture_batch:
            yield f"event: batch_progress\ndata: {json.dumps({'batch_id': batch_id, 'status': fixture_batch['status'], 'counts': fixture_batch['counts'], 'eta_seconds': fixture_batch.get('eta_seconds'), '_mock': True})}\n\n"
        queue = event_bus.subscribe(batch_id)
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            event_bus.unsubscribe(batch_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            **({"X-Mock": "true"} if fixture_batch else {}),
        },
    )


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
