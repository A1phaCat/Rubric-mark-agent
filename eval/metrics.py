"""Metric primitives for the evaluation report."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from statistics import mean, pstdev
from typing import TypeVar

T = TypeVar("T")


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


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% interval for a proportion that stays sensible for small samples and 0% or 100%."""

    if trials <= 0:
        return None
    share = successes / trials
    centre = (share + z * z / (2 * trials)) / (1 + z * z / trials)
    half = z * ((share * (1 - share) / trials + z * z / (4 * trials * trials)) ** 0.5) / (1 + z * z / trials)
    return max(0.0, centre - half), min(1.0, centre + half)


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2 + 1  # ties share the average rank
        start = end + 1
    return ranks


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Rank correlation; None when there are fewer than three pairs or no variation."""

    if len(left) != len(right) or len(left) < 3:
        return None
    a, b = _ranks(left), _ranks(right)
    ma, mb = mean(a), mean(b)
    covariance = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    scale = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return covariance / scale if scale else None


def bootstrap_interval(
    groups: Sequence[Sequence[T]],
    statistic: Callable[[list[T]], float | None],
    *,
    rounds: int = 2000,
    seed: int = 5623,
) -> tuple[float, float] | None:
    """95% percentile interval, resampling whole groups (submissions) with replacement.

    Criteria of one submission are not independent, so the submission is the unit resampled.
    """

    if len(groups) < 2:
        return None
    generator = random.Random(seed)
    values = []
    for _ in range(rounds):
        sample = [item for _ in groups for item in generator.choice(groups)]
        value = statistic(sample)
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]
