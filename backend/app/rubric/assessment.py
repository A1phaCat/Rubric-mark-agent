"""Stable rubric assessment plans used by evidence retrieval and grading."""

from __future__ import annotations

import re
from typing import Any

_VALID_MODES = {"analytic", "binary", "holistic"}
_BINARY_WORDS = re.compile(
    r"\b(meets?|does not meet|met|not met|pass|fail|yes|no|satisfied|unsatisfied)\b",
    re.IGNORECASE,
)


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or fallback


def _aspect(value: Any, position: int) -> dict[str, str] | None:
    if isinstance(value, str):
        label = value.strip()
        description = label
        source = "derived"
        aspect_id = ""
    elif isinstance(value, dict):
        label = str(value.get("label") or value.get("description") or "").strip()
        description = str(value.get("description") or label).strip()
        source = "explicit" if value.get("source") == "explicit" else "derived"
        aspect_id = str(value.get("id") or "")
    else:
        return None
    if not label:
        return None
    return {
        "id": _slug(aspect_id or label, f"aspect-{position + 1}"),
        "label": label[:240],
        "description": description[:1000],
        "source": source,
    }


def _derived_aspects(name: str, description: str, levels: list[dict[str, Any]]) -> list[dict[str, str]]:
    top = max(levels, key=lambda level: float(level.get("points") or 0), default={})
    source = str(top.get("description") or description or "").strip()
    if ":" in source:
        prefix, remainder = source.split(":", 1)
        if re.search(r"following|criteria|requirements|includes?", prefix, re.IGNORECASE):
            source = remainder.strip()
    clauses = [
        re.sub(r"^[\s\d.)-]+", "", clause).strip(" .")
        for clause in re.split(r"\s*;\s*|\n+|\s+•\s+", source)
    ]
    clauses = [clause for clause in clauses if len(clause.split()) >= 3]
    if len(clauses) < 2:
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for position, clause in enumerate(clauses[:12]):
        normalised = " ".join(clause.lower().split())
        if normalised in seen:
            continue
        seen.add(normalised)
        result.append(
            {
                "id": _slug(clause, f"aspect-{position + 1}"),
                "label": clause[:240],
                "description": clause[:1000],
                "source": "derived",
            }
        )
    return result


def normalise_assessment_plan(
    criterion: dict[str, Any], levels: list[dict[str, Any]] | None = None
) -> tuple[str, list[dict[str, str]]]:
    """Build evidence requirements when a submission is retrieved/graded.

    Old database rows may contain parser-derived aspects.  Those are ignored
    and rebuilt from the current criterion at runtime; only explicitly authored
    aspects are treated as rubric metadata.
    """

    levels = levels if levels is not None else list(criterion.get("levels") or [])
    supplied = [
        item
        for position, raw in enumerate(criterion.get("aspects") or [])
        if (item := _aspect(raw, position)) is not None
        and item["source"] == "explicit"
    ]
    mode = str(criterion.get("grading_mode") or "").lower()
    labels = " ".join(str(level.get("label") or "") for level in levels)
    if mode not in _VALID_MODES:
        mode = "binary" if len(levels) == 2 and _BINARY_WORDS.search(labels) else ""
    if supplied and not mode:
        mode = "analytic"
    if not supplied and mode not in {"binary", "holistic"}:
        supplied = _derived_aspects(
            str(criterion.get("name") or "Criterion"),
            str(criterion.get("description") or ""),
            levels,
        )
        if len(supplied) >= 2:
            mode = "analytic"
        elif not mode:
            mode = "holistic"
    if mode in {"binary", "holistic"} or not supplied:
        supplied = [
            {
                "id": "criterion",
                "label": str(criterion.get("name") or "Criterion"),
                "description": str(criterion.get("description") or criterion.get("name") or ""),
                "source": "explicit",
            }
        ]
    return mode, supplied
