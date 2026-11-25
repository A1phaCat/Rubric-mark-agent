"""Canvas as a source of rubrics and submissions (read-only)."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.canvas import CanvasClient, CanvasError, normalise_base_url
from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.core import AppSetting
from app.ingest import UnsafeArchive, expand_upload
from app.security.secrets import protect_secret, unprotect_secret
from app.services.submission_service import store_upload

URL_KEY, TOKEN_KEY, NAME_KEY = "canvas.base_url", "canvas.token", "canvas.user"
KEYCHAIN_ACCOUNT = "canvas-access-token"  # its own entry: never replaces the AI provider's key
_UNSAFE = re.compile(r"[^\w.\- ]+")


def _value(db: Session, key: str) -> str:
    item = db.get(AppSetting, key)
    return item.value_encrypted if item else ""


def _store(db: Session, key: str, value: str) -> None:
    item = db.get(AppSetting, key)
    if item is None:
        db.add(AppSetting(key=key, value_encrypted=value))
    else:
        item.value_encrypted = value


def settings_view(db: Session) -> dict[str, Any]:
    token = _value(db, TOKEN_KEY)
    return {"enabled": bool(token), "base_url": _value(db, URL_KEY) or None, "has_token": bool(token),
            "user": _value(db, NAME_KEY) or None}


def save_settings(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if "base_url" in payload:
        _store(db, URL_KEY, normalise_base_url(str(payload.get("base_url") or "")))
    if payload.get("token"):
        _store(db, TOKEN_KEY, protect_secret(str(payload["token"]).strip(), KEYCHAIN_ACCOUNT))
        _store(db, NAME_KEY, "")
    if payload.get("clear_token"):
        _store(db, TOKEN_KEY, "")
        _store(db, NAME_KEY, "")
    if payload.get("user"):
        _store(db, NAME_KEY, str(payload["user"])[:120])
    db.commit()
    return settings_view(db)


def client(db: Session, base_url: str | None = None, token: str | None = None) -> CanvasClient:
    stored = _value(db, TOKEN_KEY)
    return CanvasClient(base_url or _value(db, URL_KEY), token or (unprotect_secret(stored) if stored else ""))


async def test_connection(db: Session, base_url: str | None, token: str | None) -> dict[str, Any]:
    me = await client(db, base_url, token).me()
    return {"ok": True, "user": me.get("name") or me.get("short_name") or "", "id": me.get("id")}


def _course(item: dict[str, Any]) -> dict[str, Any]:
    term = item.get("term") if isinstance(item.get("term"), dict) else {}
    return {"id": item.get("id"), "name": item.get("name") or "", "code": item.get("course_code") or "",
            "term": term.get("name") or ""}


def _assignment(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name") or "",
        "due_at": item.get("due_at"),
        "points_possible": item.get("points_possible"),
        "has_rubric": bool(item.get("rubric")),
        "rubric_title": (item.get("rubric_settings") or {}).get("title") if item.get("rubric") else None,
        "criteria": len(item.get("rubric") or []),
        "submission_types": item.get("submission_types") or [],
        "has_submitted": bool(item.get("has_submitted_submissions")),
        "group": bool(item.get("group_category_id")),
    }


async def courses(db: Session) -> list[dict[str, Any]]:
    items = await client(db).courses()
    return [_course(item) for item in items if item.get("name") and not item.get("access_restricted_by_date")]


async def assignments(db: Session, course_id: str) -> list[dict[str, Any]]:
    return [_assignment(item) for item in await client(db).assignments(course_id)]


async def rubric_export(db: Session, course_id: str, assignment_id: str) -> tuple[str, str]:
    """The assignment's rubric in Canvas's own export shape, which the rubric parser reads as-is."""

    canvas = client(db)
    assignment = await canvas.assignment(course_id, assignment_id)
    if not assignment.get("rubric"):
        raise CanvasError("This assignment has no rubric attached in Canvas")
    course = await canvas.course(course_id)
    document = {"course": course, "assignment": assignment, "rubric": assignment["rubric"]}
    return json.dumps(document), f"canvas-{course_id}-{assignment_id}.json"


def _filename(submission: dict[str, Any], original: str) -> str:
    """Canvas download-pack style: the student's number first when Canvas shares it, so SIDs match."""

    user = submission.get("user") if isinstance(submission.get("user"), dict) else {}
    number = next((str(value) for value in (user.get("sis_user_id"), user.get("login_id"))
                   if value and str(value).isdigit()), "")
    name = _UNSAFE.sub("", str(user.get("sortable_name") or user.get("name") or "student")).replace(" ", "")
    original = _UNSAFE.sub("_", original or "submission")
    return f"SID-{number}_{name}_{original}" if number else f"{name}_canvas{submission.get('user_id')}_{original}"


async def import_submissions(db: Session, settings: Settings, batch: Batch, course_id: str,
                             assignment_id: str) -> dict[str, Any]:
    """Download every submission this token may see into the batch, as if the files were uploaded."""

    canvas = client(db)
    found, scope = await canvas.submissions(course_id, assignment_id)
    manifest: list[dict[str, Any]] = []
    seen = 0
    for submission in found:
        files: list[tuple[str, bytes, str | None]] = []
        for attachment in submission.get("attachments") or []:
            if attachment.get("url"):
                content = await canvas.download(str(attachment["url"]))
                files.append((_filename(submission, str(attachment.get("filename") or attachment.get("display_name")
                                                         or "submission")), content, attachment.get("content-type")))
        if not files and submission.get("body"):
            text = re.sub(r"<[^>]+>", " ", str(submission["body"]))
            files.append((_filename(submission, "online-text.txt"), text.encode("utf-8"), "text/plain"))
        if not files:
            continue
        seen += 1
        for name, content, mime in files:
            try:
                for candidate in expand_upload(name, content, mime):
                    manifest.append(store_upload(db, settings, batch, candidate.name, candidate.content,
                                                 candidate.declared_mime, candidate.source_archive or "Canvas"))
            except UnsafeArchive as exc:
                manifest.append({"name": name, "status": "rejected", "message": str(exc), "sid_guess": None})
    db.commit()
    return {
        "files": manifest,
        "summary": {
            "canvas_submissions": len(found),
            "scope": scope,
            "with_files": seen,
            "accepted": sum(item["status"] == "accepted" for item in manifest),
            "duplicates": sum(item["status"] == "duplicate" for item in manifest),
            "skipped": sum(item["status"] in {"unsupported", "rejected"} for item in manifest),
            "needs_sid": sum(item.get("sid_guess") is None for item in manifest if item["status"] == "accepted"),
            "likely_scanned": 0,
        },
    }
