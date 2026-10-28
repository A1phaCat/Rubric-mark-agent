"""Tools the evidence-check agent calls while it marks one criterion.

Every tool is read-only over the submission's full-text view: nothing here touches the
database or the mark. ``cite`` checks a quote against the submission the moment it is
recorded, so the model learns straight away when a quote is not the student's own words.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.protocol import ToolSpec
from app.retrieval import FullDocument, find_quote, keyword_search

_RELEVANCE = ("direct", "partial", "contradictory")
_SEARCH_RESULTS = 5
_SEARCH_CHARS = 600
_QUOTE_CHARS = 400

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "cite",
        "Record one piece of evidence: words copied exactly from one paragraph of the submission, "
        "and the aspects it bears on. The reply says whether the quote was found.",
        {
            "type": "object",
            "properties": {
                "paragraph_id": {"type": "string", "description": "Paragraph id such as p12"},
                "quote": {"type": "string", "description": "Exact words from that paragraph, one sentence or clause"},
                "aspect_ids": {"type": "array", "items": {"type": "string"}, "description": "Aspect ids it bears on"},
                "relevance": {"type": "string", "enum": list(_RELEVANCE)},
            },
            "required": ["paragraph_id", "quote", "aspect_ids", "relevance"],
        },
    ),
    ToolSpec(
        "search",
        "Search the whole submission for paragraphs about something, e.g. an aspect you have not "
        "found yet phrased in other words. Returns the best matching paragraphs with their ids.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "aspect_ids": {"type": "array", "items": {"type": "string"}, "description": "Aspects this search is for"},
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        "finish",
        "Call when the evidence is complete. Say which aspects are not addressed anywhere in the submission.",
        {"type": "object", "properties": {"notes": {"type": "string"}}, "required": ["notes"]},
    ),
)


@dataclass
class Citation:
    passage_id: str
    quote: str
    relevance: str
    aspect_ids: list[str]


@dataclass
class ToolOutcome:
    """What the model is told, plus a short structured record for the timeline."""

    reply: str
    outcome: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class EvidenceWorkspace:
    """The state of one criterion's evidence check."""

    def __init__(self, full: FullDocument, aspects: list[dict[str, Any]], max_citations: int) -> None:
        self.full = full
        self.passages = {passage.id: passage for passage in full.passages}
        self.aspects = {str(aspect["id"]): str(aspect.get("label") or aspect["id"]) for aspect in aspects}
        self.max_citations = max_citations
        self.citations: list[Citation] = []
        self.searched: set[str] = set()
        self.notes = ""
        self.finished = False

    # ------------------------------------------------------------------ queries
    def covered(self) -> set[str]:
        return {aspect for citation in self.citations for aspect in citation.aspect_ids}

    def unchecked_missing(self) -> list[str]:
        """Aspects with no evidence that the model has not searched for either."""

        return [aspect for aspect in self.aspects if aspect not in self.covered() and aspect not in self.searched]

    def gate_raw(self) -> dict[str, Any]:
        """The evidence in the format the existing evidence gate validates."""

        return {
            "evidence": [
                {
                    "passage_id": citation.passage_id,
                    "quote": citation.quote,
                    "role": "primary" if index == 0 else "supporting",
                    "relevance": citation.relevance,
                    "aspect_ids": citation.aspect_ids,
                }
                for index, citation in enumerate(self.citations)
            ],
            "notes": self.notes,
        }

    # -------------------------------------------------------------------- tools
    def run(self, name: str, arguments: dict[str, Any] | None) -> ToolOutcome:
        if arguments is None:
            return ToolOutcome("error: the arguments were not valid JSON; call the tool again", "error")
        handler = {"cite": self.cite, "search": self.search, "finish": self.finish}.get(name)
        if handler is None:
            return ToolOutcome(f"error: unknown tool {name!r}; use cite, search or finish", "error")
        return handler(arguments)

    def _aspect_ids(self, value: Any) -> tuple[list[str], list[str]]:
        values = value if isinstance(value, list) else [value] if value else []
        known = [str(item) for item in values if str(item) in self.aspects]
        unknown = [str(item) for item in values if str(item) not in self.aspects]
        if not known and len(self.aspects) == 1:
            known = list(self.aspects)
        return list(dict.fromkeys(known)), unknown

    def cite(self, arguments: dict[str, Any]) -> ToolOutcome:
        claimed = str(arguments.get("quote") or "").strip()[:_QUOTE_CHARS]
        paragraph_id = str(arguments.get("paragraph_id") or "")
        relevance = str(arguments.get("relevance") or "direct").lower()
        if relevance not in _RELEVANCE:
            relevance = "direct"
        aspect_ids, unknown = self._aspect_ids(arguments.get("aspect_ids"))
        if not aspect_ids:
            valid = ", ".join(self.aspects)
            return ToolOutcome(f"error: give at least one aspect id from: {valid}", "error",
                               detail=f"unknown aspects {unknown}" if unknown else "no aspect")
        passage = self.passages.get(paragraph_id)
        quote = find_quote(passage.text, claimed) if passage is not None else None
        relocated = False
        if quote is None and claimed:
            for candidate in self.full.passages:
                quote = find_quote(candidate.text, claimed)
                if quote is not None:
                    passage, relocated = candidate, True
                    break
        if passage is None or quote is None:
            return ToolOutcome(
                "invalid: those words are not in the submission. Copy the exact words from one paragraph.",
                "invalid", detail=claimed[:160], data={"paragraph_id": paragraph_id, "aspect_ids": aspect_ids},
            )
        key = " ".join(quote.lower().split())
        for existing in self.citations:
            if existing.passage_id == passage.id and " ".join(existing.quote.lower().split()) == key:
                existing.aspect_ids = list(dict.fromkeys(existing.aspect_ids + aspect_ids))
                return ToolOutcome("recorded (merged with the same quote already recorded)", "merged",
                                   detail=quote[:160], data={"paragraph_id": passage.id, "aspect_ids": existing.aspect_ids})
        if len(self.citations) >= self.max_citations:
            return ToolOutcome(f"limit reached: {self.max_citations} quotes are already recorded; call finish",
                               "limit")
        self.citations.append(Citation(passage.id, quote, relevance, aspect_ids))
        where = f" (found in {passage.id}, not {paragraph_id})" if relocated else ""
        note = f"; unknown aspect ids ignored: {', '.join(unknown)}" if unknown else ""
        return ToolOutcome(f"recorded{where}{note}", "relocated" if relocated else "valid", detail=quote[:160],
                           data={"paragraph_id": passage.id, "page": passage.page, "paragraph": passage.paragraph,
                                 "aspect_ids": aspect_ids, "relevance": relevance})

    def search(self, arguments: dict[str, Any]) -> ToolOutcome:
        query = str(arguments.get("query") or "").strip()
        aspect_ids, _ = self._aspect_ids(arguments.get("aspect_ids"))
        if not query:
            return ToolOutcome("error: give a search query", "error")
        if not arguments.get("aspect_ids"):
            aspect_ids = [aspect for aspect in self.aspects if aspect not in self.covered()]
        self.searched.update(aspect_ids)
        hits = keyword_search(self.full.passages, query, limit=_SEARCH_RESULTS)
        if not hits:
            return ToolOutcome("no paragraphs match that search", "none", detail=query,
                               data={"query": query, "aspect_ids": aspect_ids, "hits": []})
        lines = [
            f"[{hit.id} | p.{hit.page} {hit.paragraph}] "
            + (hit.text if len(hit.text) <= _SEARCH_CHARS else hit.text[:_SEARCH_CHARS] + " …")
            for hit in hits
        ]
        return ToolOutcome("\n".join(lines), "results", detail=query,
                           data={"query": query, "aspect_ids": aspect_ids, "hits": [hit.id for hit in hits]})

    def finish(self, arguments: dict[str, Any]) -> ToolOutcome:
        self.notes = str(arguments.get("notes") or "").strip()[:2000]
        self.finished = True
        return ToolOutcome("done", "done", detail=self.notes[:300])
