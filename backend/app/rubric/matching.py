"""Pick the closest library rubric for a set of submissions (approximate pairing).

Imported submissions rarely come with their own rubric. ``rank_rubrics`` scores every
library rubric against the assignment title and a sample of submission text with TF-IDF
cosine similarity and returns the ranking together with the shared terms, so the choice
can be recorded and audited rather than taken on trust. A low top score means the pairing
is only an approximation and should be reviewed by the tutor.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

_WORD = re.compile(r"[a-z][a-z\-]{2,}")
_STOP = frozenset(
    """the and for with that this are was were from have has had not but all any can will
    your you our their they them its into each per such than then there these those which
    who what when where how why use used using also more most other some may must should
    would could been being does did done very well good high low level marks mark points
    criterion criteria rubric assignment assessment submission submit submitted weight week
    unit due report task tasks part student students work clearly clear demonstrates shows
    provides limited little minimal some adequate excellent poor fails fail meets exceeds
    mastery near none basic""".split()
)


def tokens(text: str) -> list[str]:
    return [word for word in _WORD.findall(text.lower()) if word not in _STOP]


@dataclass(frozen=True)
class RubricCandidate:
    rubric_id: str
    title: str
    text: str  # title + criterion names, descriptions and level descriptors


@dataclass(frozen=True)
class RubricMatch:
    rubric_id: str
    title: str
    score: float
    shared_terms: tuple[str, ...]
    genre: str | None = None  # genre keyword shared by the assignment and rubric titles


# Assessment genres named in titles ("Reflective piece", "Business Report", ...). When the
# assignment title and a rubric title name the same genre the rubric gets ``genre_bonus``:
# the genre says more about which criteria apply than shared vocabulary does.
GENRES: dict[str, re.Pattern[str]] = {
    "reflective": re.compile(r"(?i)reflect|journal"),
    "essay": re.compile(r"(?i)\bessay"),
    "literature review": re.compile(r"(?i)literature|research\s+report"),
    "proposal": re.compile(r"(?i)proposal|scope"),
    "presentation": re.compile(r"(?i)presentation|\bdemo\b"),
    "short answer": re.compile(r"(?i)short\s+answer|quiz"),
    "progress report": re.compile(r"(?i)progress"),
}


def shared_genre(assignment_title: str, rubric_title: str) -> str | None:
    for genre, pattern in GENRES.items():
        if pattern.search(assignment_title) and pattern.search(rubric_title):
            return genre
    return None


def _tfidf(docs: Sequence[Counter[str]]) -> list[dict[str, float]]:
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(doc.keys())
    n = len(docs)
    vectors = []
    for doc in docs:
        total = sum(doc.values()) or 1
        vectors.append(
            {term: (count / total) * (math.log((1 + n) / (1 + df[term])) + 1) for term, count in doc.items()}
        )
    return vectors


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    norm = math.sqrt(sum(v * v for v in left.values())) * math.sqrt(sum(v * v for v in right.values()))
    return dot / norm if norm else 0.0


def rank_rubrics(
    assignment_title: str,
    sample_texts: Iterable[str],
    candidates: Sequence[RubricCandidate],
    *,
    title_weight: int = 5,
    genre_bonus: float = 0.2,
) -> list[RubricMatch]:
    """Rank ``candidates`` for one assignment; the title counts ``title_weight`` times."""

    if not candidates:
        return []
    query: Counter[str] = Counter()
    for _ in range(title_weight):
        query.update(tokens(assignment_title))
    for text in sample_texts:
        query.update(tokens(text))
    rubric_docs = [Counter(tokens(item.text)) for item in candidates]
    vectors = _tfidf([*rubric_docs, query])
    query_vector = vectors[-1]
    ranked = []
    for candidate, vector in zip(candidates, vectors[:-1]):
        shared = sorted(
            (term for term in vector if term in query_vector),
            key=lambda term: vector[term] * query_vector[term],
            reverse=True,
        )
        genre = shared_genre(assignment_title, candidate.title)
        score = _cosine(query_vector, vector) + (genre_bonus if genre else 0.0)
        ranked.append(RubricMatch(candidate.rubric_id, candidate.title, round(score, 4), tuple(shared[:8]), genre))
    return sorted(ranked, key=lambda item: item.score, reverse=True)
