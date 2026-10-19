"""University mark-band conversion."""

from .states import Level


def level_for_score(score: float) -> Level:
    if score >= 85:
        return Level.HD
    if score >= 75:
        return Level.DI
    if score >= 65:
        return Level.CR
    if score >= 50:
        return Level.PS
    return Level.FL
