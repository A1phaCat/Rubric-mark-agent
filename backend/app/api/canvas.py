from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings
from app.deps import get_current_user, get_db, get_settings
from app.integrations.canvas import CanvasError
from app.services import canvas_service

router = APIRouter(prefix="/canvas", tags=["canvas"])


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": message, "details": None}})


def _canvas(db: Session, settings: Settings):
    canvas_service.load_canvas_settings(db, settings)
    db.commit()  # end the read so the use case below can open its own transaction
    try:
        return canvas_service.source(settings)
    except canvas_service.CanvasNotConfigured as exc:
        raise _error(409, "canvas_not_connected", str(exc)) from exc
    except CanvasError as exc:
        raise _error(502, "canvas_error", str(exc)) from exc


@router.get("/courses")
def courses(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    canvas = _canvas(db, settings)
    try:
        items = canvas.courses()
    except CanvasError as exc:
        raise _error(502, "canvas_error", str(exc)) from exc
    return {"mode": canvas.mode, "items": [{"id": str(c["id"]), "name": c.get("name"),
                                            "course_code": c.get("course_code")} for c in items]}


@router.get("/courses/{course_id}/assignments")
def assignments(course_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    canvas = _canvas(db, settings)
    try:
        items = canvas.assignments(course_id)
    except CanvasError as exc:
        raise _error(502, "canvas_error", str(exc)) from exc
    return {"mode": canvas.mode, "items": [
        {"id": str(a["id"]), "name": a.get("name"), "points_possible": a.get("points_possible"),
         "due_at": a.get("due_at"), "has_rubric": bool(a.get("rubric")), "post_manually": a.get("post_manually")}
        for a in items]}


@router.post("/courses/{course_id}/assignments/{assignment_id}/import", status_code=201)
def import_assignment(course_id: str, assignment_id: str, db: Session = Depends(get_db),
                      settings: Settings = Depends(get_settings), user: dict = Depends(get_current_user)) -> dict:
    canvas = _canvas(db, settings)
    try:
        with db.begin():
            return canvas_service.import_assignment(db, settings, canvas, course_id, assignment_id, user["id"])
    except (CanvasError, ValueError) as exc:
        raise _error(422, "canvas_import_failed", str(exc)) from exc


@router.post("/batches/{batch_id}/push-grades")
def push_grades(batch_id: str, payload: dict[str, Any] | None = None, db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)) -> dict:
    payload = payload or {}
    canvas = _canvas(db, settings)
    try:
        with db.begin():
            return canvas_service.push_grades(
                db, settings, canvas, batch_id, dry_run=payload.get("dry_run", True) is not False,
                include_unconfirmed=bool(payload.get("include_unconfirmed", False)))
    except KeyError as exc:
        raise _error(404, "not_found", "Batch not found") from exc
    except CanvasError as exc:
        raise _error(409, "canvas_push_refused", str(exc)) from exc
