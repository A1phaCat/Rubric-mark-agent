"""Overall feedback for one confirmed submission: an AI draft from the confirmed marks, for a tutor to approve.

The draft is written only from what the tutor has already confirmed: each criterion's final
level, the tutor's comment, the AI rationale and where the evidence is. It never changes a mark,
and the student sees it only after a tutor approves it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.llm.json_io import extract_json
from app.llm.protocol import LLM, LLMResponse

PROMPT_VERSION = "overall-feedback-v1"
FIELDS = ("strengths", "improvements", "next_steps")
_MAX_ITEMS = {"strengths": 3, "improvements": 3, "next_steps": 2}
_MAX_TEXT = 600


def basis(criteria: list[dict[str, Any]]) -> str:
    """A fingerprint of the confirmed marks and comments the feedback was written from."""

    marks = [(str(c.get("criterion_id")), float(c.get("score") or 0), str(c.get("comment") or "").strip())
             for c in criteria]
    return hashlib.sha256(json.dumps(sorted(marks)).encode("utf-8")).hexdigest()[:16]


def prompt(report: dict[str, Any]) -> str:
    criteria = [
        {
            "criterion": c.get("name"),
            "level": c.get("band"),
            "level_description": c.get("descriptor"),
            "position": f"level {int(c.get('band_rank') or 0) + 1} of {c.get('band_count') or '?'} (1 is best)",
            "tutor_comment": c.get("comment") or "",
            "ai_rationale": c.get("internal_rationale") or "",
            "evidence_locations": [f"p.{e.get('page')} {e.get('paragraph') or ''}".strip()
                                   for e in (c.get("evidence") or [])[:4]],
        }
        for c in report.get("criteria", [])
    ]
    return f"""You are drafting the overall feedback a university tutor will review and release to a student, for the assignment "{report.get('batch', {}).get('name', '')}".

The tutor has already confirmed a level and a comment for every rubric criterion:
{json.dumps(criteria, ensure_ascii=False)}

Write only from this information. The tutor's comments take precedence over the AI rationales; never contradict them. Do not mention marks, points, levels or grades, do not introduce strengths or weaknesses that are not stated above, and do not quote the rubric. Address the student as "you", in plain, specific, encouraging language; refer to the criteria by name where it helps.

Return JSON only:
{{
  "summary": "two or three sentences on the submission as a whole",
  "strengths": ["one to three specific strengths, the most important first"],
  "improvements": ["one to three specific improvements, the most important first"],
  "next_steps": ["one or two concrete actions for the next assignment"]
}}"""


def clean(raw: Any) -> dict[str, Any]:
    """Keep the four fields, as trimmed text and short lists; anything else is dropped."""

    value = raw if isinstance(raw, dict) else {}
    result: dict[str, Any] = {"summary": " ".join(str(value.get("summary") or "").split())[:_MAX_TEXT * 2]}
    for field in FIELDS:
        items = value.get(field) if isinstance(value.get(field), list) else []
        result[field] = [" ".join(str(item).split())[:_MAX_TEXT] for item in items if str(item).strip()][:_MAX_ITEMS[field]]
    return result


def from_tutor(payload: dict[str, Any]) -> dict[str, Any]:
    """A tutor's edit: the same four fields, with list items given as lists or one per line."""

    shaped = dict(payload)
    for field in FIELDS:
        if isinstance(shaped.get(field), str):
            shaped[field] = [line.strip("•-* ").strip() for line in shaped[field].splitlines()]
    cleaned = clean(shaped)
    for field in FIELDS:  # a tutor may write more than the draft asks for
        items = shaped.get(field) if isinstance(shaped.get(field), list) else []
        cleaned[field] = [" ".join(str(item).split())[:_MAX_TEXT] for item in items if str(item).strip()][:8]
    return cleaned


async def draft(llm: LLM, report: dict[str, Any], metadata: dict[str, str] | None = None) -> tuple[dict[str, Any], LLMResponse]:
    response = await llm.complete(purpose="feedback_draft", prompt=prompt(report), metadata=metadata or {})
    feedback = clean(extract_json(response.text))
    if not feedback["summary"]:
        raise ValueError("The model returned no overall feedback; try again")
    return feedback, response
