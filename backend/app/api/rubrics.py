from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.common import translate_error
from app.config import Settings
from app.deps import get_current_user, get_db, get_settings
from app.llm import build_llm
from app.llm.json_io import extract_json
from app.rubric.parser import extract_rubric_file, parse_rubric_text
from app.services.rubric_service import RubricUseCases

router = APIRouter(prefix="/rubrics", tags=["rubrics"])
_MAX_RUBRIC_FILE_BYTES = 5 * 1024 * 1024

_DRAFT_HINTS = re.compile(
    r"(?:我(?:需要|想要)|帮我(?:写|生成|设计|创建|补全)|"
    r"(?:能否|能不能|可以|可否).{0,16}(?:写|生成|设计|创建|补全)|"
    r"请.{0,12}(?:写|生成|设计|创建|补全)|"
    r"\bI\s+(?:need|want)\b|"
    r"\b(?:can|could|would)\s+you\s+(?:write|draft|generate|create|design|complete|fill)\b|"
    r"\bplease\s+(?:write|draft|generate|create|design|complete|fill)\b|"
    r"\b(?:write|draft|generate|create|design|complete|fill)\s+(?:me\s+)?"
    r"(?:a|the|this|my)\s+rubric\b)",
    re.IGNORECASE,
)


def _is_draft_request(text: str) -> bool:
    return bool(_DRAFT_HINTS.search(text))


def _structure_errors(parsed: dict[str, Any], *, require_numbers: bool = True) -> list[str]:
    errors: list[str] = []
    criteria = parsed.get("criteria")
    if not isinstance(parsed.get("title"), str) or not parsed["title"].strip():
        errors.append("title is missing")
    if not isinstance(criteria, list) or not criteria:
        return [*errors, "criteria are missing"]
    for position, criterion in enumerate(criteria, 1):
        if not isinstance(criterion, dict):
            errors.append(f"criterion {position} is not an object")
            continue
        name = str(criterion.get("name") or "").strip()
        if not name or name.lower() in {"criterion", "criterion name", "name"}:
            errors.append(f"criterion {position} has no meaningful name")
        try:
            weight = float(criterion.get("weight") or 0)
        except (TypeError, ValueError):
            weight = 0
        if require_numbers and weight <= 0:
            errors.append(f"criterion {position} has no positive maximum")
        levels = criterion.get("levels")
        if not isinstance(levels, list) or len(levels) < 2:
            errors.append(f"criterion {position} has fewer than two levels")
            continue
        for level_position, level in enumerate(levels, 1):
            if not isinstance(level, dict):
                errors.append(f"criterion {position} level {level_position} is not an object")
                continue
            description = str(level.get("description") or "").strip()
            if not description or description.lower().startswith("describe this level"):
                errors.append(f"criterion {position} level {level_position} has no descriptor")
    return errors


def _first_number(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        matched = re.search(pattern, text, re.IGNORECASE)
        if matched:
            return float(matched.group(1))
    return None


def _draft_plan(text: str) -> dict[str, Any]:
    count = _first_number(
        [
            r"(\d+)\s*(?:个\s*)?(?:criteria|criterion|评分项|标准)",
            r"(?:criteria|criterion)\s*(?:count\s*)?(?:is|=|:)?\s*(\d+)",
        ],
        text,
    )
    level_count = _first_number(
        [r"(\d+)\s*(?:个\s*)?(?:levels?|等级)", r"(?:levels?|等级)\s*(?:is|=|:)?\s*(\d+)"],
        text,
    )
    total = _first_number(
        [
            r"(?:总分|满分)\D{0,12}(\d+(?:\.\d+)?)\s*(?:分|marks?|points?|pts?)?",
            r"(?:total(?:\s+marks?)?|out\s+of)\D{0,12}(\d+(?:\.\d+)?)",
        ],
        text,
    )
    each = _first_number(
        [
            r"(?:每个criterion|每项|每个标准)\D{0,12}(\d+(?:\.\d+)?)\s*(?:分|marks?|points?|pts?)",
            r"each(?:\s+criterion)?(?:\s+is|\s+worth)?\D{0,8}(\d+(?:\.\d+)?)\s*(?:marks?|points?|pts?)",
        ],
        text,
    )
    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:-|–|—|到|至)\s*(\d+(?:\.\d+)?)", text
    )
    score_range = (
        (float(range_match.group(1)), float(range_match.group(2))) if range_match else None
    )
    step = _first_number(
        [
            r"(?:step|increments?(?:\s+of)?|步长)\D{0,8}(\d+(?:\.\d+)?)",
            r"(?:每隔?|每)\s*(\d+(?:\.\d+)?)\s*分",
            r"(\d+(?:\.\d+)?)\s*(?:point|分)\s*(?:per|为一个)\s*(?:level|等级)",
        ],
        text,
    )
    return {
        "criterion_count": int(count) if count else None,
        "level_count": int(level_count) if level_count else None,
        "total": total,
        "each": each,
        "range": score_range,
        "step": step,
    }


def _apply_draft_plan(parsed: dict[str, Any], text: str) -> dict[str, Any]:
    plan = _draft_plan(text)
    criteria = list(parsed.get("criteria") or [])
    assumptions = list(parsed.get("assumptions") or [])
    questions = list(parsed.get("questions") or [])
    expected_count = plan["criterion_count"]
    if expected_count and len(criteria) != expected_count:
        parsed["_count_error"] = (
            f"expected {expected_count} criteria from the request, received {len(criteria)}"
        )
    score_range = plan["range"]
    weight = plan["each"]
    weight_source = "extracted"
    if weight is None and score_range:
        weight = max(score_range)
    if weight is None and plan["total"] and expected_count:
        weight = round(float(plan["total"]) / expected_count, 4)
        weight_source = "inferred"
        assumptions.append(
            {
                "code": "equal_weight_split",
                "message": f"Split {plan['total']:g} total marks equally across {expected_count} criteria.",
            }
        )
    if weight is None:
        questions.append(
            {
                "code": "criterion_marks_required",
                "message": "How many marks is each criterion worth?",
            }
        )

    scores: list[float] | None = None
    if score_range:
        low, high = sorted(score_range)
        step = float(plan["step"] or 1)
        if step <= 0:
            step = 1
        scores = []
        value = high
        while value >= low - 1e-9 and len(scores) < 30:
            scores.append(round(value, 6))
            value -= step
        if not scores or abs(scores[-1] - low) > 1e-6:
            scores.append(low)
        if plan["level_count"] and plan["level_count"] != len(scores):
            assumptions.append(
                {
                    "code": "inclusive_score_range",
                    "message": (
                        f"Used {len(scores)} levels because {low:g}–{high:g} in {step:g}-point "
                        "increments is inclusive."
                    ),
                }
            )
    elif weight is not None:
        count = int(plan["level_count"] or 4)
        count = max(2, min(count, 20))
        scores = [round(weight * (count - index - 1) / (count - 1), 6) for index in range(count)]
        if plan["level_count"] is None:
            assumptions.append(
                {
                    "code": "default_level_count",
                    "message": "Used four equal-interval scoring levels because no level count was stated.",
                }
            )

    for criterion in criteria:
        criterion.setdefault("prov", {})
        criterion["weight"] = weight
        criterion["prov"]["weight"] = weight_source if weight is not None else "missing"
        if scores is None:
            for level in criterion.get("levels") or []:
                level["points"] = level["min_score"] = level["max_score"] = None
                level.setdefault("prov", {})["points"] = "missing"
            continue
        original = list(criterion.get("levels") or [])
        rebuilt = []
        for index, score in enumerate(scores):
            source = original[index] if index < len(original) else {}
            label = str(source.get("label") or f"{score:g} points")
            rebuilt.append(
                {
                    **source,
                    "id": str(source.get("id") or f"level-{index + 1}"),
                    "label": label,
                    "points": score,
                    "min_score": score,
                    "max_score": score,
                    "min_inclusive": True,
                    "max_inclusive": True,
                    "description": str(source.get("description") or ""),
                    "prov": {
                        **dict(source.get("prov") or {}),
                        "points": "inferred",
                    },
                }
            )
        criterion["levels"] = rebuilt
    parsed["criteria"] = criteria
    parsed["total_score"] = (
        plan["total"]
        if plan["total"] is not None
        else sum(float(item.get("weight") or 0) for item in criteria)
    )
    parsed["total_score_source"] = "stated" if plan["total"] is not None else "computed"
    parsed["assumptions"] = assumptions
    parsed["questions"] = questions
    return parsed


def _warning_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("message"):
        return value
    return {"code": "parser_warning", "message": str(value)}


def _decorate_ai_fields(parsed: dict[str, Any], *, draft: bool) -> dict[str, Any]:
    text_source = "generated" if draft else "extracted"
    for criterion in parsed.get("criteria") or []:
        if not isinstance(criterion, dict):
            continue
        criterion.setdefault("description", "")
        criterion.setdefault("stated_percent", None)
        criterion.setdefault("scoring_mode", "fixed_levels")
        criterion.setdefault("score_mapping", "explicit")
        criterion.setdefault("granularity", None)
        criterion["prov"] = {
            **dict(criterion.get("prov") or {}),
            "name": text_source if criterion.get("name") else "missing",
            "weight": "extracted" if criterion.get("weight") not in (None, "") else "missing",
            "description": text_source if criterion.get("description") else "missing",
        }
        criterion.setdefault("source_text", {})
        for level in criterion.get("levels") or []:
            if not isinstance(level, dict):
                continue
            points = level.get("points", level.get("max_score"))
            level["points"] = points
            level.setdefault("min_score", points)
            level.setdefault("max_score", points)
            level.setdefault("min_inclusive", True)
            level.setdefault("max_inclusive", True)
            level["prov"] = {
                **dict(level.get("prov") or {}),
                "label": text_source if level.get("label") else "missing",
                "points": "extracted" if points is not None else "missing",
                "description": text_source if level.get("description") else "missing",
            }
            level.setdefault("source_text", {})
    return parsed


async def _ai_parse(
    text: str, source_name: str | None, settings: Settings, *, draft: bool
) -> tuple[dict[str, Any], str]:
    if draft:
        instruction = (
            "The user is describing a desired assessment rubric rather than supplying a complete "
            "one. Draft the missing criterion names, level labels, and concrete discriminating "
            "descriptions. Follow every explicit count, score range, increment, total and topic. "
            "Do not emit placeholders such as 'Criterion name', 'Level 1', or 'Describe this level'. "
            "A score range is inclusive: for example 0-3 in one-point increments means levels "
            "3, 2, 1, 0 even if the informal text calls that three levels; explain such a "
            "normalisation in warnings. Each criterion weight must equal its highest level. "
            "Descriptions must be usable by a university marker and specific to the named task. "
            "Focus on names and descriptors: application code will replace and validate all "
            "weights and level points from the user's numeric requirements. "
        )
    else:
        instruction = (
            "Extract every rubric field that is explicitly visible. Preserve the exact criterion "
            "names, maximums, level count, score values and verbatim descriptions. Never invent, "
            "merge, or rename criteria or levels, and never force HD/DI/CR/PS/FL bands. Represent "
            "missing names or descriptions as empty strings, missing numeric values as null, and "
            "missing levels as an empty array; do not use placeholder prose. When the source "
            "contains explicitly scored subcriteria, return each subcriterion as a separate "
            "criterion named 'Parent — Subcriterion', using its maximum and levels. "
        )
    prompt = (
        instruction
        + "Return JSON only with title, criteria, warnings, assumptions, and questions. Each criterion must contain name, "
        "weight, and levels. Each level must contain id, label, points, min_score, max_score, and "
        "description. Do not analyse submissions, evidence, coverage, or grading logic.\n\n"
        + ("RUBRIC REQUEST:\n" if draft else "RUBRIC SOURCE:\n")
        + text
    )
    llm = build_llm(settings)
    response = await llm.complete(
        purpose="rubric_parse", prompt=prompt, metadata={"source": source_name or "pasted"}
    )
    parsed = extract_json(response.text)
    parsed = _decorate_ai_fields(parsed, draft=draft)
    if draft:
        parsed = _apply_draft_plan(parsed, text)
    errors = _structure_errors(parsed, require_numbers=not bool(parsed.get("questions")))
    if parsed.get("_count_error"):
        errors.append(str(parsed["_count_error"]))
    if errors and draft:
        repair = await llm.complete(
            purpose="rubric_parse",
            prompt=(
                "Repair the following incomplete rubric JSON. Return the complete JSON object only. "
                "Resolve every listed error, replace all placeholders with task-specific content, "
                "and preserve the original requirements.\n\nERRORS:\n- "
                + "\n- ".join(errors)
                + "\n\nORIGINAL INPUT:\n"
                + text
                + "\n\nINCOMPLETE JSON:\n"
                + json.dumps(parsed, ensure_ascii=False)
            ),
            metadata={"source": source_name or "pasted", "repair": "true"},
        )
        parsed = extract_json(repair.text)
        parsed = _decorate_ai_fields(parsed, draft=draft)
        parsed = _apply_draft_plan(parsed, text)
        response = repair
        errors = _structure_errors(parsed, require_numbers=not bool(parsed.get("questions")))
        if parsed.get("_count_error"):
            errors.append(str(parsed["_count_error"]))
    if errors and draft:
        raise ValueError("AI rubric output remained incomplete: " + "; ".join(errors[:6]))
    if errors:
        warnings = parsed.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
        warnings.append(
            "Some rubric fields are missing and are highlighted for manual completion: "
            + "; ".join(errors[:6])
        )
        parsed["warnings"] = warnings
    criteria = parsed.get("criteria") or []
    computed_total = sum(float(item.get("weight") or 0) for item in criteria)
    parsed.setdefault("total_score", computed_total)
    parsed.setdefault("total_score_source", "computed")
    parsed.setdefault("assumptions", [])
    parsed.setdefault("questions", [])
    parsed.pop("_count_error", None)
    return parsed, response.model


@router.get("")
def list_rubrics(
    q: str | None = None,
    source: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
) -> dict:
    del source
    return RubricUseCases(db).list(q, page, page_size)


@router.post("", status_code=201)
def create_rubric(
    payload: dict[str, Any], db: Session = Depends(get_db), user: dict = Depends(get_current_user)
) -> dict:
    try:
        with db.begin():
            return RubricUseCases(db).create(payload, user["id"])
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/{rubric_id}")
def get_rubric(rubric_id: str, version: int | None = None, db: Session = Depends(get_db)) -> dict:
    del version
    try:
        return RubricUseCases(db).get(rubric_id)
    except Exception as exc:
        raise translate_error(exc) from exc


@router.put("/{rubric_id}")
def update_rubric(rubric_id: str, payload: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    try:
        with db.begin():
            return RubricUseCases(db).update(rubric_id, payload)
    except Exception as exc:
        raise translate_error(exc) from exc


@router.delete("/{rubric_id}")
def delete_rubric(rubric_id: str, version: int = Query(...), db: Session = Depends(get_db)) -> dict:
    try:
        with db.begin():
            return RubricUseCases(db).delete(rubric_id, version)
    except Exception as exc:
        raise translate_error(exc) from exc


async def _parse(text: str, source_name: str | None, settings: Settings) -> dict[str, Any]:
    draft = _is_draft_request(text)
    if draft:
        if settings.llm == "fake":
            raise ValueError("AI rubric drafting requires a configured non-fake LLM provider")
        parsed, model = await _ai_parse(text, source_name, settings, draft=True)
        parser = f"ai-draft:{model}"
    else:
        try:
            parsed = parse_rubric_text(text, source_name)
            parser = str(parsed.pop("_parser", "local-structured"))
        except ValueError:
            if settings.llm == "fake":
                raise
            parsed, model = await _ai_parse(text, source_name, settings, draft=False)
            parser = f"ai-recovery:{model}"
    warnings = [_warning_object(item) for item in parsed.pop("warnings", [])]
    if parser.startswith("ai-draft:"):
        warnings.insert(
            0,
            {
                "code": "ai_generated_content",
                "message": "AI drafted missing rubric details; review every criterion before use.",
            },
        )
    return {
        "rubric": parsed,
        "warnings": warnings,
        "assumptions": list(parsed.pop("assumptions", [])),
        "questions": list(parsed.pop("questions", [])),
        "parser": parser,
        "mode": "draft" if parser.startswith("ai-draft:") else "parsed",
        "_mock": False,
    }


@router.post("/parse")
async def parse_rubric(
    payload: dict[str, Any], settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    try:
        return await _parse(str(payload.get("text", "")), payload.get("source_name"), settings)
    except Exception as exc:
        raise translate_error(exc) from exc


@router.post("/parse-file")
async def parse_rubric_file(
    file: UploadFile = File(...), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    try:
        content = await file.read()
        if len(content) > _MAX_RUBRIC_FILE_BYTES:
            raise ValueError("Rubric files must be 5 MB or smaller")
        text = extract_rubric_file(file.filename or "rubric.txt", content)
        result = await _parse(text, file.filename, settings)
        result["file"] = {
            "name": file.filename,
            "size": len(content),
            "mime_type": file.content_type or "application/octet-stream",
        }
        return result
    except Exception as exc:
        raise translate_error(exc) from exc
