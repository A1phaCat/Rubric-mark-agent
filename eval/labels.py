"""Blind marking sheets for human markers: the submission, the rubric and an empty score column.

Each marker fills in their own copy without seeing any AI result; the report compares the
conditions with the markers and the markers with each other.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from .dataset import Case, criteria, load_rubric


def _marks(level: dict) -> str:
    low, high = float(level["min_score"]), float(level["max_score"])
    return f"{high:g}" if low == high else f"{low:g}–{high:g}"


def export(cases: list[Case], out: Path, raters: list[str]) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    submissions = out / "submissions"
    submissions.mkdir(exist_ok=True)
    rubrics_written: set[str] = set()
    rows = []
    for case in cases:
        rubric = load_rubric(case.rubric)
        if case.pdf is not None:
            shutil.copyfile(case.pdf, submissions / f"{case.id}.pdf")
        else:
            (submissions / f"{case.id}.txt").write_text(case.text, encoding="utf-8")
        if case.rubric not in rubrics_written:
            rubrics_written.add(case.rubric)
            lines = [f"# {rubric['title']} — {rubric['total']:g} marks", "", rubric["scale_note"], ""]
            for item in criteria(rubric):
                lines += [f"## {item['id']} · {item['name']} ({item['weight']:g} marks)", ""]
                lines += [f"- **{level['label']}** ({_marks(level)}): {level['description']}" for level in item["levels"]]
                lines.append("")
            (out / f"rubric-{case.rubric}.md").write_text("\n".join(lines), encoding="utf-8")
        for item in criteria(rubric):
            rows.append({"case": case.id, "criterion": item["id"], "criterion_name": item["name"],
                         "maximum": f"{item['weight']:g}", "score": "", "note": ""})
    sheets = []
    for rater in raters:
        path = out / f"marks-{rater}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["case", "criterion", "criterion_name", "maximum", "rater", "score", "note"])
            writer.writeheader()
            writer.writerows({**row, "rater": rater} for row in rows)
        sheets.append(path)
    return sheets
