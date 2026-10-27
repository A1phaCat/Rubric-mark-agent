"""The whole submission as the model reads it, plus facts software can compute about it.

Full-text grading gives the evidence step every paragraph, in order, with the same ids,
pages and character offsets the evidence highlighter uses. Nothing is chunked or left
out: a paragraph id is only the address a quote must come from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .service import RetrievedPassage, _passages

_WHOLE_PARAGRAPH = 10**9  # never split a paragraph
_CAPTION = re.compile(r"^(figure|fig\.|table)\s*\d+", re.IGNORECASE)
_REFERENCES = re.compile(
    r"^\s*(\d+(\.\d+)*\.?\s+)?(references|reference list|bibliography|works cited|sources)\s*$",
    re.IGNORECASE,
)
# Typographic variants a model tends to normalise when it quotes.
_FOLD = str.maketrans(
    {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
     "“": '"', "”": '"', "„": '"', "″": '"',
     "–": "-", "—": "-", "−": "-", " ": " ", "…": "..."}
)
_MAX_OUTLINE = 80


@dataclass(frozen=True)
class FullDocument:
    passages: list[RetrievedPassage]
    view: str
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def estimated_tokens(self) -> int:
        return estimate_tokens(self.view)


def estimate_tokens(text: str) -> int:
    """Conservative token estimate for English prose (about 3.6 characters per token)."""

    return int(len(text) / 3.6) + 1


def full_document(document: dict[str, Any]) -> FullDocument:
    passages = _passages(document, chunk_words=_WHOLE_PARAGRAPH)
    lines: list[str] = []
    outline: list[dict[str, Any]] = []
    index = 0
    in_references = False
    references = 0
    captions = 0
    words = 0
    for block in document.get("paragraphs", []):
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        if block.get("kind") == "heading":
            lines.append(f"\n## {text}")
            if len(outline) < _MAX_OUTLINE:
                outline.append({"heading": text, "page": int(block.get("page") or 1)})
            in_references = bool(_REFERENCES.match(text))
            continue
        passage = passages[index]
        index += 1
        lines.append(f"[{passage.id} | p.{passage.page} {passage.paragraph}] {passage.text}")
        words += len(passage.text.split())
        if _CAPTION.match(passage.text):
            captions += 1
        if _REFERENCES.match(passage.text):
            in_references = True  # a references title extracted as a paragraph
        elif in_references:
            references += 1
    pages = max([int(block.get("page") or 1) for block in document.get("paragraphs", [])] or [0])
    facts = {
        "pages": pages,
        "words": words,
        "paragraphs": len(passages),
        "headings": len(outline),
        "outline": outline,
        "figure_and_table_captions": captions,
        "reference_list_entries": references,
        "has_reference_list": references > 0,
    }
    return FullDocument(passages=passages, view="\n".join(lines).strip(), facts=facts)


def _fold(text: str) -> tuple[str, list[int]]:
    """Lower-case, typographic-folded, whitespace-collapsed text and its map to the original."""

    out: list[str] = []
    mapping: list[int] = []
    previous_space = True
    for position, char in enumerate(text):
        folded = char.translate(_FOLD).lower()
        for piece in folded:
            if piece.isspace():
                if previous_space:
                    continue
                piece = " "
                previous_space = True
            else:
                previous_space = False
            out.append(piece)
            mapping.append(position)
    while out and out[-1] == " ":
        out.pop()
        mapping.pop()
    return "".join(out), mapping


def find_quote(text: str, quote: str) -> str | None:
    """The exact substring of ``text`` that ``quote`` reproduces, or ``None``.

    Tolerates the differences a model introduces when it copies text — curly versus
    straight quotes, dashes, line breaks and repeated spaces, letter case — but never
    different words. Returning the original substring keeps highlights exact.
    """

    needle = quote.strip()
    if not needle:
        return None
    if needle in text:
        return needle
    folded_text, mapping = _fold(text)
    folded_needle, _ = _fold(needle)
    if len(folded_needle) < 8:
        return None
    start = folded_text.find(folded_needle)
    if start < 0:
        return None
    end = start + len(folded_needle) - 1
    return text[mapping[start] : mapping[end] + 1]
