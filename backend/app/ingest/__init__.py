"""Upload intake, archive safety, SID detection and deduplication.

Public boundary: ``inspect_upload``. It may write only immutable files through the batch/submission
services. Archive expansion and dedupe remain TODO(ingest) per DEV-GUIDE §G5; no extraction or
grading belongs here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class UploadInspection:
    sha256: str
    mime_type: str
    sid_guess: str | None
    is_duplicate: bool


class Ingestor(Protocol):
    def inspect_upload(self, path: Path) -> UploadInspection: ...


SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt", ".zip"})
_SID = re.compile(r"(?i)SID[-_ ]?(\d+)")
_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".zip": "application/zip",
}


def sid_from_filename(name: str) -> str | None:
    """``SID-40219_ASGN2.pdf`` → ``SID-40219``; ``None`` when no SID is present."""

    match = _SID.search(name or "")
    return f"SID-{match.group(1)}" if match else None


def mime_for(name: str, declared: str | None = None) -> str:
    if declared and declared != "application/octet-stream":
        return declared
    return _MIME.get(Path(name).suffix.lower(), "application/octet-stream")
