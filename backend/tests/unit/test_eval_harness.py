"""Evaluation helpers: agreement metrics and the dry-run token meter."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from eval.metrics import mean, quadratic_weighted_kappa, stdev  # noqa: E402


def test_qwk_is_one_for_identical_ratings_and_drops_with_disagreement() -> None:
    assert quadratic_weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3]) == pytest.approx(1.0)
    near = quadratic_weighted_kappa([0, 1, 2, 3], [0, 1, 3, 3])
    far = quadratic_weighted_kappa([0, 1, 2, 3], [3, 2, 1, 0])
    assert 0 < near < 1 and far < 0
    assert quadratic_weighted_kappa([2, 2], [2, 2]) == 1.0  # no expected disagreement


def test_mean_and_sample_stdev() -> None:
    assert mean([1, 2, 3]) == 2
    assert stdev([2, 2, 2]) == 0
    assert stdev([1, 3]) == pytest.approx(2 ** 0.5)
    assert stdev([5]) == 0


def test_dry_run_meter_counts_prompt_tokens_and_models_prefix_caching() -> None:
    pytest.importorskip("tiktoken")
    from eval.metered import MeteredDryRunLLM

    llm = MeteredDryRunLLM("gpt-4.1")
    rubric = [{"label": "HD", "points": 10}, {"label": "D", "points": 7.5}, {"label": "P", "points": 5}]
    prompt = "x " * 3000 + "compare every rubric level (best first):\n" + json.dumps({"levels": rubric})
    first = asyncio.run(llm.complete(purpose="criterion_grade", prompt=prompt))
    second = asyncio.run(llm.complete(purpose="criterion_grade", prompt=prompt))
    assert first.model == "gpt-4.1-dryrun"
    assert first.input_tokens > 3000 and first.output_tokens > 0
    assert first.cached_tokens == 0 and second.cached_tokens >= 1024
    assert json.loads(first.text)["level"] == "D"  # scripted: the second-best level
    assert len(llm.calls) == 2
