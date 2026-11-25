from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.common import translate_error
from app.api.rubrics import _parse
from app.canvas import CanvasError
from app.config import Settings
from app.db.models.batch import Batch
from app.deps import get_db, get_settings
from app.services import canvas_service

router = APIRouter(tags=["canvas"])


def _canvas_error(exc: CanvasError) -> HTTPException:
    status = 401 if exc.status == 401 else 502 if exc.status is None and "reach" in str(exc) else 422
    return HTTPException(status, {"error": {"code": "canvas_error", "message": str(exc), "details": None}})


@router.get("/canvas/courses")
async def list_courses(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"items": await canvas_service.courses(db)}
    except CanvasError as exc:
        raise _canvas_error(exc) from exc


@router.get("/canvas/courses/{course_id}/assignments")
async def list_assignments(course_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return {"items": await canvas_service.assignments(db, course_id)}
    except CanvasError as exc:
        raise _canvas_error(exc) from exc


@router.post("/canvas/courses/{course_id}/assignments/{assignment_id}/rubric")
async def import_rubric(
    course_id: str, assignment_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Parse the assignment's Canvas rubric exactly like an uploaded Canvas export."""

    try:
        text, name = await canvas_service.rubric_export(db, course_id, assignment_id)
        result = await _parse(text, name, settings)
        result["canvas"] = {"course_id": course_id, "assignment_id": assignment_id}
        return result
    except CanvasError as exc:
        raise _canvas_error(exc) from exc
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/batches/{batch_id}/canvas-import")
async def import_submissions(
    batch_id: str, payload: dict[str, Any], db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(404, {"error": {"code": "not_found", "message": "batch not found", "details": None}})
    try:
        return await canvas_service.import_submissions(
            db, settings, batch, str(payload.get("course_id") or ""), str(payload.get("assignment_id") or "")
        )
    except CanvasError as exc:
        db.rollback()
        raise _canvas_error(exc) from exc
