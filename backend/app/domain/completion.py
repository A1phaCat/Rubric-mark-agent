"""Pure completion and review-queue decisions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompletionCounts:
    total: int
    confirmed: int
    excluded: int
    ready: int = 0
    processing: int = 0
    failed: int = 0

    def __post_init__(self) -> None:
        values = (
            self.total,
            self.confirmed,
            self.excluded,
            self.ready,
            self.processing,
            self.failed,
        )
        if any(value < 0 for value in values):
            raise ValueError("Completion counts cannot be negative")
        if self.confirmed + self.excluded > self.total:
            raise ValueError("Confirmed plus excluded cannot exceed total")


def is_complete(counts: CompletionCounts) -> bool:
    """A batch completes only when all non-excluded items are confirmed and none failed."""
    return counts.failed == 0 and counts.confirmed == counts.total - counts.excluded


def end_card(counts: CompletionCounts) -> str:
    if is_complete(counts):
        return "complete"
    if counts.ready > 0:
        return "next"
    if counts.failed > 0:
        return "failed"
    if counts.processing > 0:
        return "waiting"
    return "empty"
