"""Submission intake, extraction bookkeeping and row projection.

One place stores uploaded bytes, one place records extraction results, and one place
turns a submission row into its API shape, so uploads, the worker, the review page
and the sample seeder all follow the same path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.core import User
from app.db.models.submission import File, Submission
from app.domain.ids import new_id
from app.domain.states import SubmissionStatus
from app.domain.timefmt import iso_utc
from app.extract.service import extract_document
from app.ingest import SUPPORTED_EXTENSIONS, mime_for, sid_from_filename

NO_TEXT_FLAGS = ["needs_manual", "no_text_layer"]


def store_upload(
    session: Session,
    settings: Settings,
    batch: Batch,
    filename: str,
    content: bytes,
    declared_mime: str | None = None,
    source_archive: str | None = None,
) -> dict[str, Any]:
    """Persist one uploaded file and its submission row; return its manifest entry."""

    digest = hashlib.sha256(content).hexdigest()
    extension = Path(filename or "submission.bin").suffix.lower()
    mime = mime_for(filename, declared_mime)
    if extension not in SUPPORTED_EXTENSIONS:
        return {
            "id": new_id("fil"),
            "name": filename,
            "size": len(content),
            "mime_type": mime,
            "sha256": digest,
            "sid_guess": None,
            "pages": None,
            "has_text_layer": None,
            "status": "unsupported",
            "duplicate_of": None,
            "message": "Unsupported file type",
            "source_archive": source_archive,
        }
    duplicate = session.scalar(
        select(File).where(File.batch_id == batch.id, File.sha256 == digest).limit(1)
    )
    if duplicate is not None:
        return {
            "id": new_id("fil"),
            "name": filename,
            "size": len(content),
            "mime_type": mime,
            "sha256": digest,
            "sid_guess": sid_from_filename(filename),
            "pages": None,
            "has_text_layer": None,
            "status": "duplicate",
            "duplicate_of": duplicate.id,
            "message": "Identical file skipped",
            "source_archive": source_archive,
        }
    now = datetime.now(timezone.utc)
    file_id, submission_id = new_id("fil"), new_id("sub")
    target_dir = settings.runtime_paths()["files"] / batch.id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{digest}{extension}"
    target.write_bytes(content)
    sid = sid_from_filename(filename)
    session.add(
        File(
            id=file_id,
            batch_id=batch.id,
            original_name=filename or "submission",
            path=str(target),
            sha256=digest,
            size=len(content),
            mime=mime,
            pages=None,
            text_layer=None,
            created_at=now,
        )
    )
    session.add(
        Submission(
            id=submission_id,
            batch_id=batch.id,
            file_id=file_id,
            sid=sid,
            status=SubmissionStatus.UPLOADED.value,
            flags_json="[]",
            version=1,
            updated_at=now,
        )
    )
    batch.total_count += 1
    # SessionLocal disables autoflush; make this digest visible to later files in
    # the same multi-file/ZIP request so exact duplicates are skipped reliably.
    session.flush()
    return {
        "id": file_id,
        "submission_id": submission_id,
        "name": filename,
        "size": len(content),
        "mime_type": mime,
        "sha256": digest,
        "sid_guess": sid,
        "pages": None,
        "has_text_layer": None,
        "status": "accepted",
        "duplicate_of": None,
        "message": None,
        "source_archive": source_archive,
        "version": 1,
    }


def apply_extraction(session: Session, submission: Submission, stored_file: File) -> dict[str, Any]:
    """Extract the stored file and record the canonical document on the submission.

    A file without a text layer (for example a scanned PDF) produces an empty
    document; the submission is then flagged for manual marking instead of being
    sent to the grader with nothing to read.
    """

    document = extract_document(Path(stored_file.path), submission.id, stored_file.mime)
    has_text = bool(document["paragraphs"])
    submission.document_json = json.dumps(document, ensure_ascii=False)
    submission.word_count = int(document["word_count"])
    submission.document_version = int(document["version"])
    submission.text_quality = "text_layer" if has_text else "no_text_layer"
    stored_file.pages = int(document["page_count"])
    stored_file.text_layer = has_text
    if not has_text:
        flags = set(json.loads(submission.flags_json or "[]")) | set(NO_TEXT_FLAGS)
        submission.flags_json = json.dumps(sorted(flags))
        submission.status = SubmissionStatus.NEEDS_OCR.value
        submission.ai_summary = "No text layer found — needs manual marking"
    submission.version += 1
    submission.updated_at = datetime.now(timezone.utc)
    session.flush()
    return document


def marker_names(session: Session) -> dict[str, str]:
    return {user.id: user.name for user in session.query(User).all()}


def submission_row(
    item: Submission,
    stored_file: File | None,
    markers: dict[str, str],
    *,
    adjusted: bool = False,
) -> dict[str, Any]:
    marker_id = item.confirmed_by or item.marker_id or item.claimed_by
    flags = json.loads(item.flags_json or "[]")
    if adjusted and "adjusted" not in flags:
        flags.append("adjusted")
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "sid": item.sid,
        "filename": stored_file.original_name if stored_file else (item.sid or item.id),
        "status": item.status,
        "ai_total": item.ai_total,
        "final_total": item.final_total,
        "final_level": item.final_level,
        "confidence": item.min_confidence,
        "progress": item.ai_summary,
        "marker": {"id": marker_id, "name": markers.get(marker_id, marker_id)}
        if marker_id
        else None,
        "flags": flags,
        "error": {
            "code": "processing_failed",
            "message": item.error_reason or "AI grading failed without an error message",
        }
        if item.status == SubmissionStatus.FAILED.value
        else None,
        "confirmed_at": iso_utc(item.confirmed_at),
        "updated_at": iso_utc(item.updated_at),
        "version": item.version,
    }
