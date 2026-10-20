from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from app.llm.protocol import LLMResponse

# Deterministic responses for automated tests. The grading pipeline has its own
# offline path (see app.grading.service); these cover the remaining purposes.
_RESPONSES: dict[str, dict[str, Any]] = {
    "criterion_grade": {
        "score": 0,
        "level": "FL",
        "rationale": "Deterministic FakeLLM response.",
        "confidence": "low",
        "evidence": [],
    },
    "evidence_gate": {"evidence": [], "notes": "Deterministic FakeLLM evidence gate."},
    "report_text": {
        "summary": "Deterministic FakeLLM summary.",
        "strengths": [],
        "improvements": [],
        "next_steps": [],
    },
}


class FakeLLM:
    """Deterministic offline provider. Available only when ``MARKER_ENV=test``."""

    async def list_models(self) -> Sequence[str]:
        return ["fake-marker-v1"]

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        del prompt, metadata
        if purpose not in _RESPONSES:
            raise ValueError(f"No FakeLLM response for purpose: {purpose}")
        return LLMResponse(text=json.dumps(_RESPONSES[purpose]), model="fake-marker-v1")
