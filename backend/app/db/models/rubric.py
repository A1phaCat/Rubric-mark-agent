from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Rubric(Base):
    __tablename__ = "rubrics"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (UniqueConstraint("rubric_id", "rubric_version", "position"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id"), nullable=False)
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    level_hd: Mapped[str] = mapped_column(Text, nullable=False)
    level_di: Mapped[str] = mapped_column(Text, nullable=False)
    level_cr: Mapped[str] = mapped_column(Text, nullable=False)
    level_ps: Mapped[str] = mapped_column(Text, nullable=False)
    level_fl: Mapped[str] = mapped_column(Text, nullable=False)
    pts_hd: Mapped[Optional[float]] = mapped_column(Float)
    pts_di: Mapped[Optional[float]] = mapped_column(Float)
    pts_cr: Mapped[Optional[float]] = mapped_column(Float)
    pts_ps: Mapped[Optional[float]] = mapped_column(Float)
    pts_fl: Mapped[Optional[float]] = mapped_column(Float)
    levels_json: Mapped[Optional[str]] = mapped_column(Text)
    grading_mode: Mapped[str] = mapped_column(String, nullable=False, default="holistic")
    aspects_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
