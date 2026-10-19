"""Context construction boundary; reads immutable extracted documents only."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ContextChunk:
    start_offset: int
    end_offset: int
    text: str


class Retriever(Protocol):
    def context_for(self, submission_id: str, criterion_id: str) -> list[ContextChunk]: ...


from .service import RetrievedPassage, retrieve_passages  # noqa: E402

__all__ = [
    "ContextChunk",
    "Retriever",
    "RetrievedPassage",
    "retrieve_passages",
]
