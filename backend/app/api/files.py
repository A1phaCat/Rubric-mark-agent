from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi import File as UploadField
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.submission import File, Submission
from app.deps import get_db, get_settings
from app.domain.ids import new_id
from app.ingest import UnsafeArchive, expand_upload, mime_for
from app.services.submission_service import store_upload

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
            upload_name = upload.filename or "submission"
            try:
                candidates = expand_upload(upload_name, content, upload.content_type)
                if not candidates:
                    manifest.append(
                        {
                            "id": new_id("fil"),
                            "name": upload_name,
                            "size": len(content),
                            "mime_type": mime_for(upload_name, upload.content_type),
                            "sha256": None,
                            "sid_guess": None,
                            "status": "unsupported",
                            "duplicate_of": None,
                            "message": "ZIP contains no supported submission files",
                            "source_archive": upload_name,
                        }
                    )
                for candidate in candidates:
                    manifest.append(
                        store_upload(
                            db,
                            settings,
                            batch,
                            candidate.name,
                            candidate.content,
                            candidate.declared_mime,
                            candidate.source_archive,
                        )
                    )
            except UnsafeArchive as exc:
                manifest.append(
                    {
                        "id": new_id("fil"),
                        "name": upload_name,
                        "size": len(content),
                        "mime_type": mime_for(upload_name, upload.content_type),
                        "sha256": None,
                        "sid_guess": None,
                        "status": "rejected",
                        "duplicate_of": None,
                        "message": str(exc),
                        "source_archive": upload_name,
                    }
                )
    db.commit()
    return {
        "files": manifest,
        "summary": {
            "accepted": sum(i["status"] == "accepted" for i in manifest),
            "duplicates": sum(i["status"] == "duplicate" for i in manifest),
            "skipped": sum(i["status"] in {"unsupported", "rejected"} for i in manifest),
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
