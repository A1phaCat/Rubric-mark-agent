"""Evaluation cases: frozen rubrics plus submissions sampled from a CSV of assignments.

The CSV has one row per submission with the columns ``assignment_name``,
``Virtual student submission`` and ``unit_name``. A prepared dataset keeps the sampled
text, so a run never depends on the CSV again and the same cases can be re-run.
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.extract.service import extract_document, text_document

RUBRICS = Path(__file__).with_name("rubrics")
PROPOSALS = Path(__file__).with_name("proposals") / "dataset.json"
SUBMISSION_COLUMN = "Virtual student submission"
# Decoys: well-written submissions for an assignment unrelated to every frozen rubric
# (end-user documentation for a software system).
DECOY_ASSIGNMENT = "FIT3047_S1_2021-User Documentation (Team) Grade-8261186"


@dataclass(frozen=True)
class Case:
    id: str
    rubric: str
    text: str
    source_row: int
    pdf: Path | None = None  # graded through the same PDF extraction as an upload
    intended: dict[str, float] | None = None  # the mark each criterion was written to deserve
    planted: dict[str, list[str]] | None = None  # aspects deliberately left out or done badly
    human: dict[str, float] | None = None  # a real marker's mark per criterion


def rubric_keys(*, csv_only: bool = False) -> list[str]:
    keys = sorted(path.stem for path in RUBRICS.glob("*.json"))
    return [key for key in keys if load_rubric(key).get("in_csv", True)] if csv_only else keys


def load_rubric(key: str) -> dict[str, Any]:
    return json.loads((RUBRICS / f"{key}.json").read_text(encoding="utf-8"))


def criteria(rubric: dict[str, Any]) -> list[dict[str, Any]]:
    """Criteria in the shape the grading pipeline receives from a batch's rubric snapshot."""

    return [
        {
            "id": item["id"],
            "name": item["name"],
            "weight": float(item["weight"]),
            "kind": item.get("kind", "content"),  # content | general (writing, referencing)
            "description": item.get("description", ""),
            "levels": item["levels"],
            "grading_mode": item.get("grading_mode", ""),
            "aspects": item.get("aspects", []),
        }
        for item in rubric["criteria"]
    ]


def document(submission_id: str, text: str) -> dict[str, Any]:
    return text_document(submission_id, submission_id, text)


def case_document(case: Case) -> dict[str, Any]:
    if case.pdf is not None:
        return extract_document(case.pdf, f"eval-{case.id}", "application/pdf")
    return document(f"eval-{case.id}", case.text)


def prepare(
    csv_path: Path,
    out: Path,
    *,
    keys: list[str],
    per_rubric: int,
    seed: int,
    min_chars: int,
) -> dict[str, Any]:
    csv.field_size_limit(1 << 30)
    wanted = {load_rubric(key)["assignment_name"]: key for key in keys}
    pools: dict[str, list[tuple[int, str]]] = {key: [] for key in keys}
    decoy_pool: list[tuple[int, str]] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), 1):
            name = row.get("assignment_name", "")
            key = wanted.get(name)
            text = (row.get(SUBMISSION_COLUMN) or "").strip()
            if key and len(text) >= min_chars:
                pools[key].append((row_number, text))
            elif name == DECOY_ASSIGNMENT and len(text) >= min_chars:
                decoy_pool.append((row_number, text))
    generator = random.Random(seed)
    cases = []
    for key in keys:
        pool = pools[key]
        if len(pool) < per_rubric:
            raise ValueError(f"{key}: only {len(pool)} submissions of at least {min_chars} characters")
        for index, (row_number, text) in enumerate(sorted(generator.sample(pool, per_rubric)), 1):
            cases.append({"id": f"{key}-{index:02d}", "rubric": key, "source_row": row_number, "text": text})
    # A separate generator, so adding decoys never changes which cases are sampled.
    decoys = [
        {"id": f"decoy-{index:02d}", "source_row": row_number, "text": text}
        for index, (row_number, text) in enumerate(
            sorted(random.Random(seed + 1).sample(decoy_pool, min(per_rubric, len(decoy_pool)))), 1
        )
    ]
    dataset = {
        "source": csv_path.name,
        "seed": seed,
        "per_rubric": per_rubric,
        "min_chars": min_chars,
        "rubrics": keys,
        "decoy_assignment": DECOY_ASSIGNMENT,
        "cases": cases,
        "decoys": decoys,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataset, indent=1, ensure_ascii=False), encoding="utf-8")
    return dataset


def load_decoys(path: Path) -> list[Case]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "decoys_from" in data:
        source = (path.parent / data["decoys_from"]).resolve()
        return load_decoys(source) if source.exists() else []
    return [Case(item["id"], "", item["text"], int(item["source_row"])) for item in data.get("decoys", [])]


def load_cases(path: Path, per_rubric: int = 0) -> list[Case]:
    """The prepared cases; with ``per_rubric`` only the first that many of each rubric."""

    data = json.loads(path.read_text(encoding="utf-8"))
    cases = [
        Case(
            item["id"],
            item["rubric"],
            item.get("text", ""),
            int(item.get("source_row", 0)),
            pdf=(path.parent / item["pdf"]).resolve() if item.get("pdf") else None,
            intended=item.get("intended"),
            planted=item.get("planted"),
            human=item.get("human"),
        )
        for item in data["cases"]
    ]
    if not per_rubric:
        return cases
    taken: dict[str, int] = {}
    selected = []
    for case in cases:
        if taken.get(case.rubric, 0) < per_rubric:
            taken[case.rubric] = taken.get(case.rubric, 0) + 1
            selected.append(case)
    return selected
