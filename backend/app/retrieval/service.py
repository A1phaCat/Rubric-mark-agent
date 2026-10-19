from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from app.config import Settings

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}")
_STOP = {
    "and", "are", "but", "for", "from", "has", "have", "into", "its", "not", "that",
    "the", "their", "this", "was", "were", "which", "with", "within", "your", "you",
    "criterion", "criteria", "marks", "mark", "points", "level", "evidence", "submission",
}
_EMBEDDERS: dict[tuple[str, str], Any] = {}
_CHUNK_WORDS = 220
_CHUNK_OVERLAP_WORDS = 40


@dataclass(frozen=True)
class RetrievedPassage:
    id: str
    page: int
    paragraph: str
    text: str
    start_offset: int
    score: float
    section: str = ""
    vector_score: float = 0.0
    lexical_score: float = 0.0


def _tokens(value: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(value) if token.lower() not in _STOP]


def _passages(document: dict[str, Any]) -> list[RetrievedPassage]:
    passages: list[RetrievedPassage] = []
    running_offset = 0
    current_section = ""
    paragraph_index = 0
    for block in document.get("paragraphs", []):
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        if block.get("kind") == "heading":
            current_section = text
            running_offset += len(text) + 2
            continue
        paragraph_index += 1
        start_offset = int(block.get("start_offset", running_offset))
        word_matches = list(re.finditer(r"\S+", text))
        chunk_starts = range(
            0,
            max(len(word_matches), 1),
            _CHUNK_WORDS - _CHUNK_OVERLAP_WORDS,
        )
        for chunk_index, word_start in enumerate(chunk_starts, 1):
            if not word_matches:
                break
            word_end = min(word_start + _CHUNK_WORDS, len(word_matches))
            char_start = word_matches[word_start].start()
            char_end = word_matches[word_end - 1].end()
            passages.append(
                RetrievedPassage(
                    id=(
                        f"p{paragraph_index}"
                        if len(word_matches) <= _CHUNK_WORDS
                        else f"p{paragraph_index}c{chunk_index}"
                    ),
                    page=int(block.get("page") or 1),
                    paragraph=str(block.get("label") or f"¶{paragraph_index}"),
                    text=text[char_start:char_end],
                    start_offset=start_offset + char_start,
                    score=0.0,
                    section=current_section,
                )
            )
            if word_end == len(word_matches):
                break
        running_offset = start_offset + len(text) + 2
    return passages


def _query_text(criterion: dict[str, Any]) -> str:
    parts = [str(criterion.get("name", "")), str(criterion.get("description", ""))]
    for level in criterion.get("levels", []):
        parts.extend((str(level.get("label", "")), str(level.get("description", ""))))
    return " ".join(part for part in parts if part.strip())


def _lexical_scores(passages: list[RetrievedPassage], query_text: str) -> list[float]:
    query = Counter(_tokens(query_text))
    docs = [Counter(_tokens(item.text)) for item in passages]
    document_frequency = Counter(token for doc in docs for token in doc)
    average_length = sum(sum(doc.values()) for doc in docs) / max(len(docs), 1)
    scores: list[float] = []
    for terms in docs:
        length = max(sum(terms.values()), 1)
        score = 0.0
        for token, query_frequency in query.items():
            frequency = terms.get(token, 0)
            if not frequency:
                continue
            inverse_frequency = math.log(
                1
                + (len(docs) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            normalised = frequency * 2.2 / (
                frequency + 1.2 * (0.25 + 0.75 * length / max(average_length, 1))
            )
            score += inverse_frequency * normalised * (1 + math.log1p(query_frequency))
        scores.append(score)
    return scores


def _normalise(vector: Iterable[float]) -> list[float]:
    values = [float(value) for value in vector]
    magnitude = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / magnitude for value in values]


def _hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    """Deterministic test vector used only by FakeLLM runs."""

    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % dimensions
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    return _normalise(vector)


def _fastembed(settings: Settings) -> Any:
    cache_dir = str(settings.runtime_paths()["cache"] / "fastembed")
    key = (settings.embedding_model, cache_dir)
    if key not in _EMBEDDERS:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Vector RAG requires fastembed; run pip install -e backend"
            ) from exc
        _EMBEDDERS[key] = TextEmbedding(
            model_name=settings.embedding_model,
            cache_dir=cache_dir,
            threads=settings.embedding_threads,
        )
    return _EMBEDDERS[key]


def _embed(settings: Settings, texts: list[str], *, query: bool = False) -> list[list[float]]:
    if settings.llm == "fake":
        return [_hash_embedding(text) for text in texts]
    values = [
        f"Represent this sentence for searching relevant passages: {text}" if query else text
        for text in texts
    ]
    return [
        _normalise(vector)
        for vector in _fastembed(settings).embed(values, batch_size=64)
    ]


def _cache_path(
    settings: Settings,
    submission_id: str,
    document_version: int,
    passages: list[RetrievedPassage],
) -> tuple[Path, str]:
    digest = hashlib.sha256(settings.embedding_model.encode("utf-8"))
    for item in passages:
        digest.update(item.id.encode("utf-8"))
        digest.update(item.text.encode("utf-8"))
    fingerprint = digest.hexdigest()
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", submission_id)
    filename = f"{safe_id}-v{document_version}-{fingerprint[:16]}.json"
    return settings.runtime_paths()["index"] / filename, fingerprint


def _document_vectors(
    settings: Settings,
    passages: list[RetrievedPassage],
    submission_id: str,
    document_version: int,
) -> list[list[float]]:
    path, fingerprint = _cache_path(settings, submission_id, document_version, passages)
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if (
                cached.get("fingerprint") == fingerprint
                and cached.get("model") == settings.embedding_model
                and len(cached.get("vectors", [])) == len(passages)
            ):
                return [[float(value) for value in row] for row in cached["vectors"]]
        except (OSError, ValueError, TypeError):
            pass

    texts = [
        f"Section: {item.section}\nPage: {item.page}\n{item.text}"
        if item.section
        else f"Page: {item.page}\n{item.text}"
        for item in passages
    ]
    vectors = _embed(settings, texts)
    payload = {
        "version": 1,
        "submission_id": submission_id,
        "document_version": document_version,
        "model": settings.embedding_model,
        "dimensions": len(vectors[0]) if vectors else 0,
        "fingerprint": fingerprint,
        "passage_ids": [item.id for item in passages],
        "vectors": vectors,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)
    return vectors


def retrieve_passages(
    document: dict[str, Any],
    criterion: dict[str, Any],
    limit: int = 12,
    *,
    settings: Settings | None = None,
    submission_id: str = "submission",
    document_version: int = 1,
) -> list[RetrievedPassage]:
    """Hybrid dense-vector and BM25 retrieval over page-aware paragraphs."""

    passages = _passages(document)
    if not passages:
        return []
    query_text = _query_text(criterion)
    lexical = _lexical_scores(passages, query_text)
    if settings is None:
        ranked = sorted(
            (
                replace(item, score=lexical[index], lexical_score=lexical[index])
                for index, item in enumerate(passages)
            ),
            key=lambda item: (-item.score, item.page, item.paragraph),
        )
        return ranked[: max(1, limit)]

    vectors = _document_vectors(settings, passages, submission_id, document_version)
    query_vector = _embed(settings, [query_text], query=True)[0]
    dense = [sum(a * b for a, b in zip(vector, query_vector)) for vector in vectors]
    dense_order = sorted(range(len(passages)), key=lambda index: (-dense[index], index))
    lexical_order = sorted(range(len(passages)), key=lambda index: (-lexical[index], index))
    pool_size = min(len(passages), max(20, limit * 2))
    fused: dict[int, float] = {}
    for rank, index in enumerate(dense_order[:pool_size], 1):
        fused[index] = fused.get(index, 0.0) + 1.0 / (60 + rank)
    for rank, index in enumerate(lexical_order[:pool_size], 1):
        fused[index] = fused.get(index, 0.0) + 1.0 / (60 + rank)

    final_order = sorted(
        fused,
        key=lambda index: (-fused[index], -dense[index], -lexical[index], index),
    )[: max(1, limit)]
    return [
        replace(
            passages[index],
            score=fused[index],
            vector_score=dense[index],
            lexical_score=lexical[index],
        )
        for index in final_order
    ]
