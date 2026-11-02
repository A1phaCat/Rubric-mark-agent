"""Canvas use cases: connection settings, assignment import, grade write-back.

Write-back is a dry run unless the caller passes ``dry_run=False``; a live push is refused
unless the Canvas assignment uses manual posting, so pushed grades stay hidden from
students (draft) until a teacher posts them in Canvas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.core import AppSetting
from app.db.models.review import Review
from app.db.models.rubric import RubricCriterion
from app.db.models.submission import AIResult, Submission
from app.ingest import SUPPORTED_EXTENSIONS
from app.integrations.canvas import (
    CanvasAPI,
    CanvasError,
    CanvasSource,
    OfflineCanvas,
    grade_update,
    rubric_export,
)
from app.rubric.parser import parse_rubric_text
from app.security.secrets import protect_secret, unprotect_secret
from app.services.batch_service import BatchUseCases
from app.services.rubric_service import RubricUseCases
from app.services.submission_service import store_upload


class CanvasNotConfigured(CanvasError):
    pass


def _values(db: Session) -> dict[str, str]:
    return {item.key: item.value_encrypted for item in db.query(AppSetting).filter(AppSetting.key.like("canvas.%"))}


def _store(db: Session, key: str, value: str) -> None:
    item = db.get(AppSetting, key)
    if item is None:
        db.add(AppSetting(key=key, value_encrypted=value))
    else:
        item.value_encrypted = value


def load_canvas_settings(db: Session, settings: Settings) -> Settings:
    values = _values(db)
    settings.canvas_base_url = values.get("canvas.base_url") or settings.canvas_base_url
    if values.get("canvas.offline_dir"):
        settings.canvas_offline_dir = Path(values["canvas.offline_dir"])
    if values.get("canvas.token"):
        settings.canvas_token = unprotect_secret(values["canvas.token"])
    return settings


def describe(settings: Settings) -> dict[str, Any]:
    live = bool(settings.canvas_base_url and settings.canvas_token)
    offline = bool(settings.canvas_offline_dir and Path(settings.canvas_offline_dir).is_dir())
    return {
        "enabled": live or offline,
        "mode": "api" if live else ("offline" if offline else None),
        "base_url": settings.canvas_base_url,
        "has_token": bool(settings.canvas_token),
        "offline_dir": str(settings.canvas_offline_dir) if settings.canvas_offline_dir else None,
    }


def save_settings(db: Session, settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
    if "base_url" in payload:
        url = str(payload.get("base_url") or "").strip().rstrip("/")
        if url and not url.startswith("https://"):
            raise ValueError("Canvas base_url must start with https://")
        _store(db, "canvas.base_url", url)
        settings.canvas_base_url = url or None
    if payload.get("token"):
        _store(db, "canvas.token", protect_secret(str(payload["token"])))
        settings.canvas_token = str(payload["token"])
    if "offline_dir" in payload:
        folder = str(payload.get("offline_dir") or "")
        _store(db, "canvas.offline_dir", folder)
        settings.canvas_offline_dir = Path(folder) if folder else None
    return describe(settings)


def source(settings: Settings) -> CanvasSource:
    if settings.canvas_base_url and settings.canvas_token:
        return CanvasAPI(settings.canvas_base_url, settings.canvas_token)
    if settings.canvas_offline_dir and Path(settings.canvas_offline_dir).is_dir():
        return OfflineCanvas(Path(settings.canvas_offline_dir))
    raise CanvasNotConfigured("Canvas is not connected: add a base URL and token, or an export folder")


def _link_key(batch_id: str) -> str:
    return f"canvas.link.{batch_id}"


def import_assignment(
    db: Session, settings: Settings, canvas: CanvasSource, course_id: str, assignment_id: str, actor_id: str
) -> dict[str, Any]:
    """Create a library rubric, a draft batch and its submissions from one Canvas assignment."""

    course = canvas.course(course_id)
    assignment = canvas.assignment(course_id, assignment_id)
    export = rubric_export(course, assignment)
    parsed = parse_rubric_text(json.dumps(export), f"canvas-{assignment_id}.json")
    rubric = RubricUseCases(db).create(
        {"title": parsed["title"], "source": parsed.get("source") or "Canvas", "criteria": parsed["criteria"]},
        actor_id,
    )["rubric"]
    batches = BatchUseCases(db)
    created = batches.create(
        {"name": str(assignment.get("name") or f"Canvas assignment {assignment_id}"),
         "unit": course.get("course_code"), "rubric_id": rubric["id"], "rubric_version": rubric.get("version", 1),
         "due_at": assignment.get("due_at")},
        actor_id,
    )
    batch = db.get(Batch, created["batch"]["id"])
    assert batch is not None
    batches.snapshot_rubric(batch)
    users: dict[str, str] = {}
    files: list[dict[str, Any]] = []
    skipped = 0
    for item in canvas.submissions(course_id, assignment_id):
        attachments = [a for a in item.get("attachments") or []
                       if Path(str(a.get("filename") or a.get("display_name") or "")).suffix.lower() in SUPPORTED_EXTENSIONS]
        if not attachments:
            skipped += 1
            continue
        attachment = attachments[-1]
        user = item.get("user") or {}
        user_id = str(item.get("user_id") or user.get("id"))
        sid = str(user.get("sis_user_id") or f"canvas-{user_id}")
        # The stored name carries no student name: Canvas user id + the file's own name.
        entry = store_upload(db, settings, batch, f"{user_id}_{attachment.get('filename') or attachment.get('display_name')}",
                             canvas.download(attachment), attachment.get("content-type"))
        if entry.get("status") == "accepted":
            submission = db.get(Submission, entry["submission_id"])
            assert submission is not None
            submission.sid = sid
            users[submission.id] = user_id
        files.append({k: entry.get(k) for k in ("name", "status", "submission_id", "message")})
    _store(db, _link_key(batch.id), json.dumps({"course_id": str(course_id), "assignment_id": str(assignment_id),
                                                "mode": canvas.mode, "users": users}))
    db.flush()
    return {"rubric_id": rubric["id"], "batch_id": batch.id, "imported": len(users), "skipped_without_file": skipped,
            "files": files, "mode": canvas.mode}


def _criteria(db: Session, batch: Batch, submission: Submission) -> list[dict[str, Any]]:
    rows = db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_id == batch.rubric_library_id,
                                                    RubricCriterion.rubric_version == batch.rubric_version)
                      .order_by(RubricCriterion.position))
    ai = {r.criterion_id: r for r in db.scalars(select(AIResult).where(AIResult.submission_id == submission.id))}
    reviews = {r.criterion_id: r for r in db.scalars(select(Review).where(Review.submission_id == submission.id))}
    out = []
    for criterion in rows:
        review, result = reviews.get(criterion.id), ai.get(criterion.id)
        score = review.score if review is not None and review.score is not None else (result.score if result else None)
        if score is None:
            continue
        out.append({"name": criterion.name, "score": score, "comment": (review.comment if review else "") or None})
    return out


def push_grades(
    db: Session, settings: Settings, canvas: CanvasSource, batch_id: str, *,
    dry_run: bool = True, include_unconfirmed: bool = False,
) -> dict[str, Any]:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise KeyError(batch_id)
    link_row = db.get(AppSetting, _link_key(batch_id))
    if link_row is None:
        raise CanvasError("This batch was not imported from Canvas")
    link = json.loads(link_row.value_encrypted)
    assignment = canvas.assignment(link["course_id"], link["assignment_id"])
    if not dry_run and canvas.mode == "api" and not assignment.get("post_manually"):
        raise CanvasError("The Canvas assignment posts grades automatically; switch it to manual posting so "
                          "pushed grades stay hidden until you post them")
    requests, skipped = [], []
    for submission_id, user_id in link["users"].items():
        submission = db.get(Submission, submission_id)
        if submission is None:
            continue
        confirmed = submission.final_total is not None
        if not confirmed and not include_unconfirmed:
            skipped.append({"submission_id": submission_id, "reason": "not confirmed by a marker"})
            continue
        criteria = _criteria(db, batch, submission)
        if not criteria:
            skipped.append({"submission_id": submission_id, "reason": "no scores yet"})
            continue
        total = submission.final_total if confirmed else sum(item["score"] for item in criteria)
        body = grade_update(assignment.get("rubric"), criteria, total)
        requests.append({"submission_id": submission_id, "user_id": user_id, "confirmed": confirmed,
                         "method": "PUT",
                         "path": f"/api/v1/courses/{link['course_id']}/assignments/{link['assignment_id']}/submissions/{user_id}",
                         "body": body})
    sent = 0
    if not dry_run:
        for item in requests:
            canvas.put_grade(link["course_id"], link["assignment_id"], item["user_id"], item["body"])
            sent += 1
    return {"dry_run": dry_run, "mode": canvas.mode, "would_send": len(requests), "sent": sent,
            "skipped": skipped, "requests": requests}
