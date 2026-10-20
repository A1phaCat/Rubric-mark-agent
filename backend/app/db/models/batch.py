from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    term_id: Mapped[str] = mapped_column(ForeignKey("terms.id"), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False)
    rubric_library_id: Mapped[Optional[str]] = mapped_column(ForeignKey("rubrics.id"))
    rubric_version: Mapped[Optional[int]] = mapped_column(Integer)
    rubric_snapshot_json: Mapped[Optional[str]] = mapped_column(Text)
    model_provider: Mapped[Optional[str]] = mapped_column(String)
    model_name: Mapped[Optional[str]] = mapped_column(String)
    prompt_version: Mapped[Optional[str]] = mapped_column(String)
    external_processing_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Sample batches are seeded by app.sample.seed and listed before user batches.
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Pinned batches are listed first (newest first). New batches start pinned.
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finalised_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
