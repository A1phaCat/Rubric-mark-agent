"""Usage-record interface; persistence belongs to the LLM module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.db.models.llm import LLMCall
from app.domain.ids import new_id


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    submission_id: str | None
    prompt_version: str
    cached_tokens: int = 0


class UsageSink(Protocol):
    def record(self, usage: UsageRecord) -> None: ...


class SQLAlchemyUsageSink:
    """Persists provider metadata and token counts, never prompts or student text."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, usage: UsageRecord) -> None:
        self.session.add(
            LLMCall(
                id=new_id("llm"),
                provider=usage.provider,
                model=usage.model,
                purpose=usage.purpose,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_tokens=usage.cached_tokens,
                latency_ms=usage.latency_ms,
                cost_usd=0,
                submission_id=usage.submission_id,
                prompt_version=usage.prompt_version,
                created_at=datetime.now(timezone.utc),
            )
        )
        self.session.flush()
