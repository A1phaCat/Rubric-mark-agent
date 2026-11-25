"""University mark-band conversion.

Bands are defined on the percentage of the rubric maximum, so a 28/30 rubric total
and an 93/100 total both land in HD.
"""

from typing import List, Tuple

from .states import Level

# (level, inclusive lower bound in percent), highest first.
BANDS: Tuple[Tuple[Level, float], ...] = (
    (Level.HD, 85.0),
    (Level.DI, 75.0),
    (Level.CR, 65.0),
    (Level.PS, 50.0),
    (Level.FL, 0.0),
)

BAND_NAMES = {
    Level.HD: "High Distinction",
    Level.DI: "Distinction",
    Level.CR: "Credit",
    Level.PS: "Pass",
    Level.FL: "Fail",
}


def percent(score: float, maximum: float) -> float:
    return 100.0 * score / maximum if maximum > 0 else 0.0


def level_for_percent(value: float) -> Level:
    for level, lower in BANDS:
        if value >= lower - 1e-9:
            return level
    return Level.FL


def level_for_score(score: float, maximum: float) -> Level:
    """Band for ``score`` out of ``maximum`` (the rubric total, not 100)."""

    return level_for_percent(percent(score, maximum))


def band_ranges() -> List[Tuple[Level, float, float]]:
    """(level, lower %, upper %) for histogram bins; upper is exclusive except for HD."""

    ranges = []
    upper = 100.0
    for level, lower in BANDS:
        ranges.append((level, lower, upper))
        upper = lower
    return ranges
