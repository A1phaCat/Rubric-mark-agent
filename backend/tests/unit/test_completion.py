import pytest

from app.domain.completion import CompletionCounts, end_card, is_complete


def test_complete_uses_confirmed_equals_total_minus_excluded() -> None:
    assert is_complete(CompletionCounts(total=10, confirmed=8, excluded=2))


def test_unresolved_failure_blocks_completion() -> None:
    counts = CompletionCounts(total=10, confirmed=8, excluded=2, failed=1)
    assert not is_complete(counts)
    assert end_card(counts) == "failed"


def test_waiting_and_next_cards() -> None:
    assert end_card(CompletionCounts(10, 4, 0, ready=1, processing=5)) == "next"
    assert end_card(CompletionCounts(10, 4, 0, processing=6)) == "waiting"


def test_impossible_counts_rejected() -> None:
    with pytest.raises(ValueError):
        CompletionCounts(total=1, confirmed=1, excluded=1)
