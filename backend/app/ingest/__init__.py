"""Upload intake helpers: safe archive expansion and deterministic SID detection."""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Protocol
from zipfile import BadZipFile, ZipFile, ZipInfo


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
_NINE_DIGIT_SID = re.compile(r"(?<!\d)(\d{9})(?!\d)")
_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".zip": "application/zip",
}


def sid_from_filename(name: str) -> str | None:
    """Read an explicit ``SID-`` token, or a standalone nine-digit student number."""

    match = _SID.search(name or "")
    if not match:
        match = _NINE_DIGIT_SID.search(name or "")
    return f"SID-{match.group(1)}" if match else None


def mime_for(name: str, declared: str | None = None) -> str:
    if declared and declared != "application/octet-stream":
        return declared
    return _MIME.get(Path(name).suffix.lower(), "application/octet-stream")


@dataclass(frozen=True)
class UploadCandidate:
    name: str
    content: bytes
    declared_mime: str | None = None
    source_archive: str | None = None


class UnsafeArchive(ValueError):
    """Raised when a ZIP cannot be expanded within the intake safety limits."""


MAX_ARCHIVE_FILES = 2_000
MAX_ARCHIVE_MEMBER_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


def _safe_member_name(info: ZipInfo) -> str | None:
    raw = info.filename.replace("\\", "/")
    path = PurePosixPath(raw)
    if info.is_dir() or not raw:
        return None
    if raw.startswith("/") or ".." in path.parts:
        raise UnsafeArchive(f"Unsafe ZIP path: {raw}")
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise UnsafeArchive(f"ZIP symlink is not supported: {raw}")
    if any(part in {"__MACOSX", ".DS_Store"} for part in path.parts):
        return None
    return str(path)


def expand_upload(
    filename: str, content: bytes, declared_mime: str | None = None
) -> list[UploadCandidate]:
    """Return one candidate per submission, expanding a ZIP without writing it to disk.

    Paths, symlinks, encrypted members, oversized archives and suspicious compression
    ratios are rejected before any member is persisted.
    """

    if Path(filename).suffix.lower() != ".zip":
        return [UploadCandidate(filename, content, declared_mime)]
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > MAX_ARCHIVE_FILES:
                raise UnsafeArchive(f"ZIP contains more than {MAX_ARCHIVE_FILES} files")
            total = 0
            candidates: list[UploadCandidate] = []
            for info in infos:
                safe_name = _safe_member_name(info)
                if safe_name is None:
                    continue
                if info.flag_bits & 0x1:
                    raise UnsafeArchive(f"Encrypted ZIP member is not supported: {safe_name}")
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise UnsafeArchive(f"ZIP member is larger than 50 MB: {safe_name}")
                if info.file_size and info.compress_size == 0:
                    raise UnsafeArchive(f"Suspicious ZIP compression ratio: {safe_name}")
                if (
                    info.compress_size
                    and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise UnsafeArchive(f"Suspicious ZIP compression ratio: {safe_name}")
                total += info.file_size
                if total > MAX_ARCHIVE_TOTAL_BYTES:
                    raise UnsafeArchive("ZIP expands beyond the 512 MB safety limit")
                if Path(safe_name).suffix.lower() == ".zip":
                    raise UnsafeArchive(f"Nested ZIP files are not supported: {safe_name}")
                member = archive.read(info)
                if len(member) != info.file_size:
                    raise UnsafeArchive(f"ZIP member size changed while reading: {safe_name}")
                candidates.append(
                    UploadCandidate(safe_name, member, mime_for(safe_name), filename)
                )
            return candidates
    except BadZipFile as exc:
        raise UnsafeArchive("The uploaded ZIP is invalid or corrupted") from exc
