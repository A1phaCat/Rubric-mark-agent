"""Golden-set metric primitives; datasets are intentionally not bundled."""

from __future__ import annotations

from collections.abc import Sequence


def mean_absolute_error(expected: Sequence[float], actual: Sequence[float]) -> float:
    if len(expected) != len(actual) or not expected:
        raise ValueError("Expected and actual must have equal non-zero length")
    return sum(abs(left - right) for left, right in zip(expected, actual)) / len(expected)


def level_agreement(expected: Sequence[str], actual: Sequence[str]) -> float:
    if len(expected) != len(actual) or not expected:
        raise ValueError("Expected and actual must have equal non-zero length")
    return sum(left == right for left, right in zip(expected, actual)) / len(expected)


def quadratic_weighted_kappa(
    expected: Sequence[int], actual: Sequence[int], min_rating: int | None = None, max_rating: int | None = None
) -> float:
    """Cohen's kappa with quadratic weights over integer ratings (e.g. rubric level indices).

    1.0 is perfect agreement, 0 is chance level. When both raters give one identical
    constant rating the expected disagreement is zero and the agreement is reported as 1.0.
    """

    if len(expected) != len(actual) or not expected:
        raise ValueError("Expected and actual must have equal non-zero length")
    low = min(min(expected), min(actual)) if min_rating is None else min_rating
    high = max(max(expected), max(actual)) if max_rating is None else max_rating
    size = high - low + 1
    observed = [[0.0] * size for _ in range(size)]
    for left, right in zip(expected, actual):
        observed[left - low][right - low] += 1
    n = float(len(expected))
    row = [sum(observed[i]) for i in range(size)]
    col = [sum(observed[i][j] for i in range(size)) for j in range(size)]
    numerator = denominator = 0.0
    for i in range(size):
        for j in range(size):
            weight = ((i - j) ** 2) / ((size - 1) ** 2) if size > 1 else 0.0
            numerator += weight * observed[i][j]
            denominator += weight * row[i] * col[j] / n
    return 1.0 if denominator == 0 else 1.0 - numerator / denominator


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def stdev(values: Sequence[float]) -> float:
    """Sample standard deviation (n-1); 0.0 for fewer than two values."""

    if len(values) < 2:
        return 0.0
    centre = mean(values)
    return (sum((value - centre) ** 2 for value in values) / (len(values) - 1)) ** 0.5

