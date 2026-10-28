from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class File(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String, nullable=False)
    pages: Mapped[Optional[int]] = mapped_column(Integer)
    text_layer: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False, index=True)
    file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("files.id"))
    sid: Mapped[Optional[str]] = mapped_column(String, index=True)
    student_name: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    error_reason: Mapped[Optional[str]] = mapped_column(Text)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    text_quality: Mapped[Optional[str]] = mapped_column(String)
    document_json: Mapped[Optional[str]] = mapped_column(Text)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ai_total: Mapped[Optional[float]] = mapped_column(Float)
    ai_level: Mapped[Optional[str]] = mapped_column(String)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    min_confidence: Mapped[Optional[str]] = mapped_column(String)
    final_total: Mapped[Optional[float]] = mapped_column(Float)
    final_level: Mapped[Optional[str]] = mapped_column(String)
    confirmed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    claimed_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    excluded_reason: Mapped[Optional[str]] = mapped_column(Text)
    marker_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Reviewed, student-facing summary (summary/strengths/improvements/next_steps).
    feedback_json: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AIResult(Base):
    __tablename__ = "ai_results"
    # One AI result per criterion of a submission: two worker slots can never both store one.
    __table_args__ = (
        Index("uq_ai_results_submission_criterion", "submission_id", "criterion_id", unique=True),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    criterion_id: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    minor_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    coverage_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sufficiency: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    confidence: Mapped[str] = mapped_column(String, nullable=False)
    self_confidence: Mapped[Optional[float]] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The evidence check's steps (tutor view only); null when the step ran in one pass.
    trace_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ai_result_id: Mapped[str] = mapped_column(ForeignKey("ai_results.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[Optional[int]] = mapped_column(Integer)
    para: Mapped[Optional[str]] = mapped_column(String)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
