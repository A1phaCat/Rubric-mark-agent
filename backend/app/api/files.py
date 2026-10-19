from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi import File as UploadField
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.submission import File, Submission
from app.deps import get_db, get_settings
from app.domain.ids import new_id

router = APIRouter(prefix="/batches", tags=["files"])


@router.post("/{batch_id}/files")
async def upload_files(
    batch_id: str,
    files: list[UploadFile] = UploadField(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(404, "batch not found")
    manifest = []
    with db.begin_nested():
        for upload in files:
            content = await upload.read()
            digest = hashlib.sha256(content).hexdigest()
            extension = Path(upload.filename or "submission.bin").suffix.lower()
            if extension not in {".pdf", ".docx", ".txt", ".zip"}:
                manifest.append(
                    {
                        "id": new_id("fil"),
                        "name": upload.filename,
                        "size": len(content),
                        "mime_type": upload.content_type or "application/octet-stream",
                        "sha256": digest,
                        "sid_guess": None,
                        "pages": None,
                        "has_text_layer": None,
                        "status": "unsupported",
                        "duplicate_of": None,
                        "message": "Unsupported file type",
                    }
                )
                continue
            file_id, submission_id = new_id("fil"), new_id("sub")
            target_dir = settings.runtime_paths()["files"] / batch_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{digest}{extension}"
            target.write_bytes(content)
            sid_match = re.search(r"(?i)SID[-_ ]?(\d+)", upload.filename or "")
            sid_guess = sid_match.group(1) if sid_match else None
            db.add(
                File(
                    id=file_id,
                    batch_id=batch_id,
                    original_name=upload.filename or "submission",
                    path=str(target),
                    sha256=digest,
                    size=len(content),
                    mime=upload.content_type or "application/octet-stream",
                    pages=None,
                    text_layer=None,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.add(
                Submission(
                    id=submission_id,
                    batch_id=batch_id,
                    file_id=file_id,
                    sid=f"SID-{sid_guess}" if sid_guess else None,
                    status="uploaded",
                    flags_json="[]",
                    is_mock=False,
                    version=1,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            batch.total_count += 1
            manifest.append(
                {
                    "id": file_id,
                    "submission_id": submission_id,
                    "name": upload.filename,
                    "size": len(content),
                    "mime_type": upload.content_type or "application/octet-stream",
                    "sha256": digest,
                    "sid_guess": f"SID-{sid_guess}" if sid_guess else None,
                    "pages": None,
                    "has_text_layer": None,
                    "status": "accepted",
                    "duplicate_of": None,
                    "message": None,
                }
            )
    db.commit()
    return {
        "files": manifest,
        "summary": {
            "accepted": sum(i["status"] == "accepted" for i in manifest),
            "duplicates": 0,
            "skipped": sum(i["status"] != "accepted" for i in manifest),
            "needs_sid": sum(i["sid_guess"] is None for i in manifest if i["status"] == "accepted"),
            "likely_scanned": 0,
        },
    }


@router.delete("/{batch_id}/files/{file_id}")
def delete_file(batch_id: str, file_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.get(File, file_id)
    if item is None or item.batch_id != batch_id:
        raise HTTPException(404, "file not found")
    batch = db.get(Batch, batch_id)
    if batch is None or batch.status != "draft":
        raise HTTPException(409, "file manifest is locked")
    submission = db.query(Submission).filter(Submission.file_id == file_id).one_or_none()
    if submission:
        db.delete(submission)
    db.delete(item)
    batch.total_count = max(0, batch.total_count - 1)
    db.commit()
    return {"deleted": True, "file_id": file_id}
