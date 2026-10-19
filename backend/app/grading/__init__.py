"""Criterion grading and verbatim evidence verification boundary."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GradeResult:
    criterion_id: str
    score: float
    confidence: str
    rationale: str


class Grader(Protocol):
    async def grade(self, submission_id: str, criterion_id: str) -> GradeResult: ...


from .service import grade_criterion  # noqa: E402

__all__ = ["GradeResult", "Grader", "grade_criterion"]
