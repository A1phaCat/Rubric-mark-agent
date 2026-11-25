from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.files import upload_files
from app.config import Settings
from app.db.base import Base
from app.db.models.batch import Batch
from app.ingest import UnsafeArchive, expand_upload, sid_from_filename
from app.services.submission_service import store_upload


def _zip(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_zip_expands_nested_folders_and_matches_sids() -> None:
    candidates = expand_upload(
        "canvas-export.zip",
        _zip(
            {
                "group-a/SID-12345_report.txt": b"first",
                "group-b/student_490123456_final.txt": b"second",
                "__MACOSX/._report.txt": b"metadata",
            }
        ),
        "application/zip",
    )

    assert [item.name for item in candidates] == [
        "group-a/SID-12345_report.txt",
        "group-b/student_490123456_final.txt",
    ]
    assert [sid_from_filename(item.name) for item in candidates] == [
        "SID-12345",
        "SID-490123456",
    ]
    assert all(item.source_archive == "canvas-export.zip" for item in candidates)


def test_zip_rejects_path_traversal() -> None:
    with pytest.raises(UnsafeArchive, match="Unsafe ZIP path"):
        expand_upload("unsafe.zip", _zip({"../SID-1.txt": b"no"}))


def test_zip_rejects_nested_archives() -> None:
    with pytest.raises(UnsafeArchive, match="Nested ZIP"):
        expand_upload("outer.zip", _zip({"inner.zip": _zip({"SID-1.txt": b"x"})}))


def test_identical_files_are_skipped_within_one_batch(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, autoflush=False)
    batch = Batch(
        id="bat_zip",
        name="ZIP intake",
        term_id="term_test",
        status="draft",
        total_count=0,
        created_by="usr_test",
        created_at=datetime.now(timezone.utc),
        version=1,
    )
    session.add(batch)
    settings = Settings(data_dir=tmp_path)

    first = store_upload(session, settings, batch, "SID-1.txt", b"same")
    duplicate = store_upload(session, settings, batch, "SID-2.txt", b"same")

    assert first["status"] == "accepted"
    assert duplicate["status"] == "duplicate"
    assert duplicate["duplicate_of"] == first["id"]
    assert batch.total_count == 1


@pytest.mark.asyncio
async def test_zip_upload_returns_only_unmatched_files_for_attention(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine, autoflush=False)
    batch = Batch(
        id="bat_api_zip",
        name="ZIP API intake",
        term_id="term_test",
        status="draft",
        total_count=0,
        created_by="usr_test",
        created_at=datetime.now(timezone.utc),
        version=1,
    )
    session.add(batch)
    session.flush()
    archive = UploadFile(
        filename="submissions.zip",
        file=BytesIO(
            _zip(
                {
                    "class/SID-1.txt": b"same submission",
                    "class/SID-2-copy.txt": b"same submission",
                    "class/unknown-student.txt": b"different submission",
                }
            )
        ),
    )

    result = await upload_files(
        batch.id,
        files=[archive],
        db=session,
        settings=Settings(data_dir=tmp_path),
    )

    assert result["summary"] == {
        "accepted": 2,
        "duplicates": 1,
        "skipped": 0,
        "needs_sid": 1,
        "likely_scanned": 0,
    }
    assert [item["name"] for item in result["files"] if item["status"] == "accepted"] == [
        "class/SID-1.txt",
        "class/unknown-student.txt",
    ]
    assert batch.total_count == 2

