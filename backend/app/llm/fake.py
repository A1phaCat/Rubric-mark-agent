from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from app.llm.protocol import ChatResponse, LLMResponse, ToolCall, ToolSpec

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


_PARAGRAPH = re.compile(r"^\[(p\d+) \|[^\]]*\] (.+)$", re.MULTILINE)
_ASPECTS = re.compile(r"^ASPECT IDS: (.+)$", re.MULTILINE)


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

    async def chat(
        self,
        *,
        purpose: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        metadata: Mapping[str, str] | None = None,
    ) -> ChatResponse:
        """Scripted evidence check: cite the first paragraphs, search for the rest, finish."""

        del purpose, tools, metadata
        text = "\n".join(str(message.get("content") or "") for message in messages)
        paragraphs = _PARAGRAPH.findall(text)
        aspect_match = _ASPECTS.search(text)
        aspects = [item.strip() for item in aspect_match.group(1).split(",")] if aspect_match else []
        turn = sum(1 for message in messages if message.get("role") == "assistant")
        calls: list[ToolCall] = []
        if turn == 0:
            for index, (paragraph_id, body) in enumerate(paragraphs[:2]):
                quote = body.split(". ")[0][:200]
                assigned = aspects[index:index + 1] or aspects[:1]
                calls.append(_call(f"fake_{index}", "cite", {"paragraph_id": paragraph_id, "quote": quote,
                                                            "aspect_ids": assigned, "relevance": "direct"}))
        elif turn == 1 and len(aspects) > 2:
            calls.append(_call("fake_search", "search", {"query": aspects[2].replace("-", " "),
                                                          "aspect_ids": [aspects[2]]}))
        else:
            calls.append(_call("fake_finish", "finish", {"notes": "Deterministic FakeLLM evidence check."}))
        return ChatResponse(text="", tool_calls=tuple(calls), model="fake-marker-v1", finish_reason="tool_calls")


def _call(call_id: str, name: str, arguments: dict[str, Any]) -> ToolCall:
    raw = json.dumps(arguments)
    return ToolCall(id=call_id, name=name, raw_arguments=raw, arguments=arguments)
