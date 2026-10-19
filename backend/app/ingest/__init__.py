"""Upload intake, archive safety, SID detection and deduplication.

Public boundary: ``inspect_upload``. It may write only immutable files through the batch/submission
services. TODO(ingest): implement DEV-GUIDE §G5; no extraction or grading belongs here.
"""

from __future__ import annotations

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
