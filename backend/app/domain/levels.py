"""A criterion's own performance levels.

Rubrics use their own scales — HD…FL, Exceeds/Mastery/Near/Below, Full/Partial/No credit,
two to six levels, different per criterion — so a criterion score is always placed on that
criterion's levels, never on the university grade bands (those apply only to the total; see
``bands.py``).

A level covers the scores up to its ``points``: with levels 5 / 3.99 / 3 / 1.99 / 0.99 a score
of 3.5 is the 3.99 level. ``min_score``/``max_score`` from the rubric take precedence when the
rubric states an explicit range.
"""

from __future__ import annotations

from typing import Any, Iterable


def _points(level: dict[str, Any]) -> float:
    value = level.get("points", level.get("max_score"))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ordered(levels: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Levels from best to lowest (by points; ties keep the rubric order)."""

    items = [item for item in levels if isinstance(item, dict)]
    return sorted(items, key=_points, reverse=True)


def with_ranges(levels: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give every level a score range ending at its points and starting above the next level.

    Used for rubrics (such as Canvas exports) whose levels are bands rather than exact marks.
    The lowest level starts at zero.
    """

    items = ordered(levels)
    result = []
    for index, level in enumerate(items):
        lower = _points(items[index + 1]) if index + 1 < len(items) else 0.0
        top = _points(level)
        result.append(
            {
                **level,
                "max_score": top,
                "max_inclusive": True,
                "min_score": min(lower, top),
                "min_inclusive": index + 1 >= len(items) or lower >= top,
            }
        )
    return result


def level_for(levels: Iterable[dict[str, Any]], score: float | None) -> dict[str, Any] | None:
    """The level a score falls in: the lowest-scoring level whose points are at least ``score``."""

    items = ordered(levels)
    if not items or score is None:
        return None
    value = float(score)
    for level in items:
        low = level.get("min_score")
        high = level.get("max_score")
        if low is not None and high is not None and float(low) < float(high):
            above_low = value > float(low) or (level.get("min_inclusive", True) and value >= float(low))
            if above_low and value <= float(high) + 1e-9:
                return level
    chosen = items[0]
    for level in items:
        if _points(level) + 1e-9 >= value:
            chosen = level
    return chosen


def rank(levels: Iterable[dict[str, Any]], level: dict[str, Any] | None) -> tuple[int, int]:
    """(position from the top, number of levels) — 0 is the best level."""

    items = ordered(levels)
    if level is None or not items:
        return (len(items), len(items))
    for index, item in enumerate(items):
        if item is level or (item.get("id"), item.get("label")) == (level.get("id"), level.get("label")):
            return (index, len(items))
    return (len(items), len(items))


def has_descriptors(levels: Iterable[dict[str, Any]]) -> bool:
    return any(str(item.get("description") or "").strip() for item in levels if isinstance(item, dict))
