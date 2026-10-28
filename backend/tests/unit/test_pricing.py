"""Token prices: cost arithmetic, model-name matching and the shipped table."""

import json
from pathlib import Path

import pytest

from app.llm.pricing import DEFAULT_TABLE, load_table, parse_table

TABLE = parse_table(
    {
        "checked_at": "2026-10-28",
        "models": {
            "gpt-4.1": {"input": 2.0, "cached_input": 0.5, "output": 8.0, "source": "openai"},
            "gpt-4.1-mini": {"input": 0.4, "cached_input": 0.1, "output": 1.6, "source": "openai"},
            "MiniMax-M3": {"input": 0.3, "output": 1.2, "source": "minimax"},
        },
    }
)


def test_cached_tokens_are_part_of_input_and_billed_at_the_cache_price() -> None:
    # 800 uncached x $2 + 200 cached x $0.5 + 500 output x $8, per million tokens
    assert TABLE.cost("gpt-4.1", 1000, 500, 200) == pytest.approx(0.0057)


def test_cached_tokens_never_exceed_input() -> None:
    assert TABLE.cost("gpt-4.1", 100, 0, 500) == pytest.approx(100 * 0.5 / 1e6)


def test_missing_cache_price_falls_back_to_input_price() -> None:
    assert TABLE.cost("MiniMax-M3", 1000, 0, 1000) == pytest.approx(1000 * 0.3 / 1e6)


def test_dated_snapshots_use_the_longest_matching_name() -> None:
    assert TABLE.price_for("gpt-4.1-2025-04-14").model == "gpt-4.1"
    assert TABLE.price_for("gpt-4.1-mini-2025-04-14").model == "gpt-4.1-mini"
    assert TABLE.price_for("minimax-m3").model == "MiniMax-M3"


def test_unknown_models_are_unpriced_not_free() -> None:
    assert TABLE.price_for("my-azure-deployment") is None
    assert TABLE.cost("my-azure-deployment", 1000, 1000) is None
    assert TABLE.cost(None, 1000, 1000) is None
    # a different model that merely shares a prefix is not matched
    assert TABLE.price_for("gpt-4.10") is None


def test_shipped_table_is_dated_sourced_and_complete() -> None:
    data = json.loads(DEFAULT_TABLE.read_text(encoding="utf-8"))
    assert data["currency"] == "USD" and data["checked_at"]
    for name, row in data["models"].items():
        assert row["source"] in data["sources"], name
        assert row["input"] >= 0 and row["output"] >= 0, name
    table = load_table(DEFAULT_TABLE)
    for model in ("gpt-4.1", "gpt-4o-mini", "MiniMax-M3", "fake-marker-v1"):
        assert table.price_for(model) is not None, model


def test_pricing_file_can_be_replaced(tmp_path: Path) -> None:
    custom = tmp_path / "prices.json"
    custom.write_text(
        json.dumps({"checked_at": "2026-11-01", "models": {"uni-gpt": {"input": 1, "output": 2}}}),
        encoding="utf-8",
    )
    table = load_table(custom)
    assert table.checked_at == "2026-11-01"
    assert table.cost("uni-gpt", 1_000_000, 1_000_000) == pytest.approx(3.0)
