"""Metric primitives for the evaluation report."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import mean, pstdev


def mean_absolute_error(expected: Sequence[float], actual: Sequence[float]) -> float:
    if len(expected) != len(actual) or not expected:
        raise ValueError("Expected and actual must have equal non-zero length")
    return sum(abs(left - right) for left, right in zip(expected, actual)) / len(expected)


def level_agreement(expected: Sequence[object], actual: Sequence[object]) -> float:
    if len(expected) != len(actual) or not expected:
        raise ValueError("Expected and actual must have equal non-zero length")
    return sum(left == right for left, right in zip(expected, actual)) / len(expected)


def adjacent_agreement(expected: Sequence[int], actual: Sequence[int]) -> float:
    """Share of pairs whose level ranks differ by at most one."""

    if len(expected) != len(actual) or not expected:
        raise ValueError("Expected and actual must have equal non-zero length")
    return sum(abs(left - right) <= 1 for left, right in zip(expected, actual)) / len(expected)


def quadratic_weighted_kappa(expected: Sequence[int], actual: Sequence[int], categories: int | None = None) -> float:
    """Cohen's kappa with quadratic weights on ordinal ranks (0 = best level)."""

    if len(expected) != len(actual) or not expected:
        raise ValueError("Expected and actual must have equal non-zero length")
    size = categories or (max(max(expected), max(actual)) + 1)
    if size < 2:
        return 1.0
    observed = [[0.0] * size for _ in range(size)]
    for left, right in zip(expected, actual):
        observed[left][right] += 1
    total = len(expected)
    rows = [sum(row) for row in observed]
    cols = [sum(observed[i][j] for i in range(size)) for j in range(size)]
    numerator = denominator = 0.0
    for i in range(size):
        for j in range(size):
            weight = (i - j) ** 2 / (size - 1) ** 2
            numerator += weight * observed[i][j]
            denominator += weight * rows[i] * cols[j] / total
    return 1.0 if denominator == 0 else 1 - numerator / denominator


def spread(values: Sequence[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def average(values: Sequence[float]) -> float | None:
    return mean(values) if values else None
