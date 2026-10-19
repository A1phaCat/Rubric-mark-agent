from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JobPayload(BaseModel):
    kind: Literal[
        "ingest", "extract", "index", "grade", "summarize", "report", "export", "demo_progress"
    ]
    batch_id: str | None = None
    submission_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class IngestJob(BaseModel):
    kind: Literal["ingest"] = "ingest"
    batch_id: str
    file_id: str


class ExtractJob(BaseModel):
    kind: Literal["extract"] = "extract"
    submission_id: str
    document_version: int = 1


class IndexJob(BaseModel):
    kind: Literal["index"] = "index"
    submission_id: str
    document_version: int


class GradeJob(BaseModel):
    kind: Literal["grade"] = "grade"
    submission_id: str
    rubric_id: str
    rubric_version: int


class SummarizeJob(BaseModel):
    kind: Literal["summarize"] = "summarize"
    submission_id: str


class ReportJob(BaseModel):
    kind: Literal["report"] = "report"
    submission_id: str
    audience: Literal["internal", "student"] = "internal"


class ExportJob(BaseModel):
    kind: Literal["export"] = "export"
    batch_id: str
    export_type: Literal["csv", "pdf_bundle"]


class DemoProgressJob(BaseModel):
    kind: Literal["demo_progress"] = "demo_progress"
    batch_id: str
    ready_delta: int = 1
