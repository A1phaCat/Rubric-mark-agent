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


from .full_text import FullDocument, estimate_tokens, find_quote, full_document  # noqa: E402
from .service import QuoteLocation, RetrievedPassage, locate_quote, retrieve_passages  # noqa: E402

__all__ = [
    "ContextChunk",
    "FullDocument",
    "estimate_tokens",
    "find_quote",
    "full_document",
    "QuoteLocation",
    "Retriever",
    "RetrievedPassage",
    "locate_quote",
    "retrieve_passages",
]
