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


def quadratic_weighted_kappa(expected: Sequence[int], actual: Sequence[int]) -> float:
    """Interface placeholder; implement with the approved evaluation dependency in M4."""
    raise NotImplementedError("QWK runner is a Phase M4 implementation task")

