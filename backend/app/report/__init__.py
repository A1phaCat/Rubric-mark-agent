"""Internal/student report composition and HTML/PDF rendering boundary.

``project_for_audience`` is the single place that decides what a student may see:
the student projection drops AI scores, confidence and internal rationale, and shows overall
feedback only once a tutor has approved it.
HTML/PDF rendering remains TODO(report) per DEV-GUIDE §G10.
"""

from __future__ import annotations

import copy
from typing import Any, Protocol

_STUDENT_HIDDEN_TOP = ("ai_total", "adjustment")
_STUDENT_HIDDEN_CRITERION = ("ai_score", "confidence", "internal_rationale")
_STUDENT_FEEDBACK = ("summary", "strengths", "improvements", "next_steps", "approved_by_name")


def project_for_audience(report: dict[str, Any], audience: str) -> dict[str, Any]:
    if audience not in {"internal", "student"}:
        raise ValueError(f"Unknown report audience: {audience}")
    projected = copy.deepcopy(report)
    projected["audience"] = audience
    if audience == "student":
        for key in _STUDENT_HIDDEN_TOP:
            projected.pop(key, None)
        for criterion in projected.get("criteria", []):
            for key in _STUDENT_HIDDEN_CRITERION:
                criterion.pop(key, None)
        feedback = projected.get("feedback")
        if isinstance(feedback, dict):
            # A draft is the tutor's to review: the student sees overall feedback only once approved.
            projected["feedback"] = (
                {key: feedback[key] for key in _STUDENT_FEEDBACK if key in feedback}
                if feedback.get("status") == "approved" else None
            )
    return projected


class ReportRenderer(Protocol):
    def render_html(self, submission_id: str, audience: str) -> str: ...
    def render_pdf(self, submission_id: str, audience: str) -> bytes: ...
