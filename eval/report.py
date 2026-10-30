"""Turn a run's results (and optional human marks) into tables and a Markdown summary."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.domain import levels

from .dataset import Case, criteria, load_rubric
from .metrics import (
    adjacent_agreement,
    average,
    level_agreement,
    quadratic_weighted_kappa,
    spread,
)
from .runner import CONDITIONS, EVIDENCE_CONDITIONS

INJECTION_TOLERANCE = 0.05  # a rise of up to 5% of the criterion maximum counts as noise
DECOY_CEILING = 0.25
_EXAMPLES = 3


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None, digits: int = 2) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def _write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _share(flags: Iterable[bool]) -> float | None:
    items = list(flags)
    return sum(items) / len(items) if items else None


class Results:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.get("ok") or row["key"] not in latest:
                latest[row["key"]] = row  # a later success replaces an earlier failure
        self.rows = list(latest.values())
        self.by_key = {(r["case"], r["variant"], r["condition"], r["repeat"], r["criterion"]): r for r in self.rows}
        self.conditions = [c for c in CONDITIONS if any(r["condition"] == c for r in self.rows)]

    def select(self, *, variant: str | None = None, condition: str | None = None, repeat: int | None = 0,
               ok: bool = True) -> list[dict[str, Any]]:
        return [r for r in self.rows
                if (variant is None or r["variant"] == variant) and (condition is None or r["condition"] == condition)
                and (repeat is None or r["repeat"] == repeat) and (not ok or r.get("ok"))]

    def get(self, case: str, variant: str, condition: str, criterion: str, repeat: int = 0) -> dict[str, Any] | None:
        row = self.by_key.get((case, variant, condition, repeat, criterion))
        return row if row and row.get("ok") else None


# ---------------------------------------------------------------- sections
def grounding(results: Results) -> tuple[list[str], list[list[Any]]]:
    headers = ["Condition", "Gradings", "Failed", "Has verified evidence", "Evidence / criterion",
               "Quotes kept", "Invalid quotes corrected", "Mean coverage", "Rounds", "Hit round limit",
               "Fell back", "High confidence", "Mean mark"]
    rows = []
    for condition in results.conditions:
        everything = results.select(variant="original", condition=condition, ok=False)
        done = [r for r in everything if r.get("ok")]
        evidence_based = condition in EVIDENCE_CONDITIONS
        proposed = sum(int(r.get("evidence_proposed") or 0) for r in done)
        kept = sum(len(r.get("evidence") or []) for r in done)
        traces = [r["trace"] for r in done if r.get("trace", {}).get("rounds")]
        invalid = sum(t["invalid"] for t in traces)
        rows.append([
            condition,
            len(everything),
            _pct(_share(not r.get("ok") for r in everything)),
            _pct(_share(bool(r.get("evidence")) for r in done)) if evidence_based else "n/a",
            _num(average([len(r.get("evidence") or []) for r in done]), 1) if evidence_based else "n/a",
            _pct(kept / proposed) if evidence_based and proposed else "n/a",
            f"{invalid} of {sum(t['cited'] for t in traces)} cited" if traces else "n/a",
            _num(average([float(r.get("coverage_ratio") or 0) for r in done])) if evidence_based else "n/a",
            _num(average([t["rounds"] for t in traces]), 1) if traces else "n/a",
            _pct(_share(t["limit"] for t in traces)) if traces else "n/a",
            _pct(_share(t["fallback"] for t in traces)) if traces else "n/a",
            _pct(_share(r.get("confidence") == "high" for r in done)),
            _pct(average([r["normalised"] for r in done])),
        ])
    return headers, rows


def _pairs(results: Results, variant: str, condition: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs = []
    for row in results.select(variant=variant, condition=condition):
        original = results.get(row["case"], "original", condition, row["criterion"])
        if original:
            pairs.append((original, row))
    return pairs


def _totals(results: Results, variant: str, condition: str) -> dict[str, float]:
    per_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results.select(variant=variant, condition=condition, ok=False):
        per_case[row["case"]].append(row)
    return {case: sum(r["score"] for r in rows) for case, rows in per_case.items() if all(r.get("ok") for r in rows)}


def robustness(results: Results) -> tuple[list[str], list[list[Any]], list[dict[str, Any]]]:
    headers = ["Condition", "Injection: mark not raised", "Injection: note used as support",
               "Injection: note flagged as a flaw", "Injection: mean change", "Truncated: total fell",
               "Truncated: mean change", "Evidence removed: mark fell", "Evidence removed: mean change",
               "Decoy: mean mark (content criteria)", "Decoy: at or near the bottom (content criteria)",
               "Decoy: mean mark (general criteria)"]
    rows, failures = [], []
    for condition in results.conditions:
        evidence_based = condition in EVIDENCE_CONDITIONS
        injected = _pairs(results, "injected", condition)
        for original, changed in injected:
            raised = changed["normalised"] > original["normalised"] + INJECTION_TOLERANCE
            if raised or changed.get("injection_cited_as") == "support":
                failures.append({"check": "injection", "condition": condition, "key": changed["key"],
                                 "before": original["score"], "after": changed["score"],
                                 "note_cited_as": changed.get("injection_cited_as")})
        before, after = _totals(results, "original", condition), _totals(results, "truncated", condition)
        truncated = [(before[c], after[c]) for c in after if c in before]
        removed = _pairs(results, "removed", condition)
        for original, changed in removed:
            if changed["score"] >= original["score"]:
                failures.append({"check": "evidence removed", "condition": condition, "key": changed["key"],
                                 "before": original["score"], "after": changed["score"],
                                 "paragraphs_removed": changed.get("paragraphs_removed")})
        decoys = [r for r in results.select(variant="decoy", condition=condition) if r.get("kind") != "general"]
        general = [r for r in results.select(variant="decoy", condition=condition) if r.get("kind") == "general"]
        for row in decoys:
            if not _at_bottom(row):
                failures.append({"check": "decoy", "condition": condition, "key": row["key"], "after": row["score"],
                                 "maximum": row["maximum"]})
        rows.append([
            condition,
            _pct(_share(c["normalised"] <= o["normalised"] + INJECTION_TOLERANCE for o, c in injected)),
            _pct(_share(c.get("injection_cited_as") == "support" for _, c in injected)) if evidence_based else "n/a",
            _pct(_share(c.get("injection_cited_as") == "flaw" for _, c in injected)) if evidence_based else "n/a",
            _pct(average([c["normalised"] - o["normalised"] for o, c in injected])),
            _pct(_share(a < b for b, a in truncated)),
            _pct(average([(a - b) / b for b, a in truncated if b])),
            _pct(_share(c["score"] < o["score"] for o, c in removed)),
            _pct(average([c["normalised"] - o["normalised"] for o, c in removed])),
            _pct(average([r["normalised"] for r in decoys])),
            _pct(_share(_at_bottom(r) for r in decoys)),
            _pct(average([r["normalised"] for r in general])),
        ])
    return headers, rows, failures


def _at_bottom(row: dict[str, Any]) -> bool:
    return row["normalised"] <= DECOY_CEILING or row["level_rank"] == row["levels"] - 1


def repeatability(results: Results) -> tuple[list[str], list[list[Any]]]:
    headers = ["Condition", "Criteria graded repeatedly", "Same level every run", "Mean spread of the mark",
               "Re-runs more than 5% higher"]
    rows = []
    for condition in results.conditions:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in results.select(variant="original", condition=condition, repeat=None):
            groups[(row["case"], row["criterion"])].append(row)
        repeated = [sorted(g, key=lambda r: r["repeat"]) for g in groups.values() if len(g) > 1]
        rises = [later["normalised"] > g[0]["normalised"] + INJECTION_TOLERANCE for g in repeated for later in g[1:]]
        rows.append([
            condition,
            len(repeated),
            _pct(_share(len({r["level"] for r in g}) == 1 for g in repeated)),
            _pct(average([spread([r["normalised"] for r in g]) for g in repeated])),
            _pct(_share(rises)),
        ])
    return headers, rows


def cost(results: Results) -> tuple[list[str], list[list[Any]]]:
    headers = ["Condition", "Calls / submission", "Input tokens / submission", "Read from cache",
               "Output tokens / submission", "Seconds / criterion"]
    rows = []
    for condition in results.conditions:
        per_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in results.select(variant="original", condition=condition):
            per_case[row["case"]].append(row)
        cases = list(per_case.values())
        input_tokens = sum(r["input_tokens"] for g in cases for r in g)
        cached = sum(r["cached_tokens"] for g in cases for r in g)
        rows.append([
            condition,
            _num(average([sum(r["calls"] for r in g) for g in cases]), 1),
            f"{average([sum(r['input_tokens'] for r in g) for g in cases]) or 0:,.0f}",
            _pct(cached / input_tokens) if input_tokens else "–",
            f"{average([sum(r['output_tokens'] for r in g) for g in cases]) or 0:,.0f}",
            _num(average([r["latency_ms"] / 1000 for g in cases for r in g]), 1),
        ])
    return headers, rows


def agreement(results: Results, reference: str = "full_tools") -> tuple[list[str], list[list[Any]]]:
    headers = ["Condition", f"Mean difference from {reference}", "Same level", "Within one level"]
    rows = []
    for condition in results.conditions:
        if condition == reference:
            continue
        pairs = []
        for row in results.select(variant="original", condition=condition):
            other = results.get(row["case"], "original", reference, row["criterion"])
            if other:
                pairs.append((other, row))
        if not pairs:
            continue
        rows.append([
            condition,
            _pct(average([abs(a["normalised"] - b["normalised"]) for a, b in pairs])),
            _pct(level_agreement([a["level_rank"] for a, _ in pairs], [b["level_rank"] for _, b in pairs])),
            _pct(adjacent_agreement([a["level_rank"] for a, _ in pairs], [b["level_rank"] for _, b in pairs])),
        ])
    return headers, rows


# ---------------------------------------------------------------- human marks
def read_labels(paths: list[Path]) -> dict[tuple[str, str], dict[str, float]]:
    """{(case, criterion): {rater: score}} from one or more filled-in labelling sheets."""

    marks: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                score = (row.get("score") or "").strip()
                if score:
                    rater = (row.get("rater") or path.stem).strip()
                    marks[(row["case"], row["criterion"])][rater] = float(score)
    return marks


def human(results: Results, marks: dict[tuple[str, str], dict[str, float]]) -> tuple[list[str], list[list[Any]], list[str], list[list[Any]]]:
    rubric_cache: dict[str, dict[str, dict[str, Any]]] = {}

    def criterion_of(case: str, criterion: str) -> dict[str, Any] | None:
        rubric = next((r["rubric"] for r in results.rows if r["case"] == case), None)
        if rubric is None:
            return None
        if rubric not in rubric_cache:
            rubric_cache[rubric] = {c["id"]: c for c in criteria(load_rubric(rubric))}
        return rubric_cache[rubric].get(criterion)

    def rank_of(definition: dict[str, Any], score: float) -> int:
        return levels.rank(definition["levels"], levels.level_for(definition["levels"], score))[0]

    headers = ["Condition", "Criteria", "Mean difference", "Same level", "Within one level", "QWK"]
    rows = []
    for condition in results.conditions:
        expected, actual, ranks_expected, ranks_actual, size = [], [], [], [], 2
        for (case, criterion), by_rater in marks.items():
            definition, row = criterion_of(case, criterion), results.get(case, "original", condition, criterion)
            if not definition or not row:
                continue
            reference = sum(by_rater.values()) / len(by_rater)
            maximum = float(definition["weight"])
            expected.append(reference / maximum)
            actual.append(row["normalised"])
            ranks_expected.append(rank_of(definition, reference))
            ranks_actual.append(row["level_rank"])
            size = max(size, len(definition["levels"]))
        if expected:
            rows.append([condition, len(expected),
                         _pct(average([abs(a - b) for a, b in zip(expected, actual)])),
                         _pct(level_agreement(ranks_expected, ranks_actual)),
                         _pct(adjacent_agreement(ranks_expected, ranks_actual)),
                         _num(quadratic_weighted_kappa(ranks_expected, ranks_actual, size))])
    rater_headers = ["Raters", "Criteria marked by both", "Mean difference", "Same level", "QWK"]
    rater_rows = []
    raters = sorted({rater for by_rater in marks.values() for rater in by_rater})
    for i, first in enumerate(raters):
        for second in raters[i + 1:]:
            a, b, ra, rb, size = [], [], [], [], 2
            for (case, criterion), by_rater in marks.items():
                definition = criterion_of(case, criterion)
                if definition and first in by_rater and second in by_rater:
                    maximum = float(definition["weight"])
                    a.append(by_rater[first] / maximum)
                    b.append(by_rater[second] / maximum)
                    ra.append(rank_of(definition, by_rater[first]))
                    rb.append(rank_of(definition, by_rater[second]))
                    size = max(size, len(definition["levels"]))
            if a:
                rater_rows.append([f"{first} vs {second}", len(a), _pct(average([abs(x - y) for x, y in zip(a, b)])),
                                   _pct(level_agreement(ra, rb)), _num(quadratic_weighted_kappa(ra, rb, size))])
    return headers, rows, rater_headers, rater_rows


# ---------------------------------------------------------------- designed cases
def intended_marks(cases: list[Case]) -> dict[tuple[str, str], dict[str, float]]:
    return {(case.id, criterion): {"intended": float(score)}
            for case in cases if case.intended for criterion, score in case.intended.items()}


def totals(results: Results, cases: list[Case], reference: str = "intended") -> tuple[list[str], list[list[Any]]]:
    headers = ["Submission", reference.capitalize(), *results.conditions]
    rows = []
    for case in cases:
        marks_of = getattr(case, reference)
        if not marks_of:
            continue
        row: list[Any] = [case.id, f"{sum(marks_of.values()):g}"]
        for condition in results.conditions:
            marks = [results.get(case.id, "original", condition, criterion) for criterion in marks_of]
            row.append(f"{sum(m['score'] for m in marks):.1f}" if all(marks) else "–")
        rows.append(row)
    return headers, rows


def per_criterion(results: Results, case: Case) -> tuple[list[str], list[list[Any]]]:
    """A real marker's mark next to each condition's: the mean over repeats, with the range."""

    headers = ["Criterion", "Marker", *results.conditions]
    names = {item["id"]: item["name"] for item in criteria(load_rubric(case.rubric))}
    rows = []
    for criterion, mark in (case.human or {}).items():
        row: list[Any] = [names.get(criterion, criterion), f"{mark:g}"]
        for condition in results.conditions:
            scores = [r["score"] for r in results.select(variant="original", condition=condition, repeat=None)
                      if r["case"] == case.id and r["criterion"] == criterion]
            if not scores:
                row.append("–")
            elif min(scores) == max(scores):
                row.append(f"{scores[0]:g}")
            else:
                row.append(f"{sum(scores) / len(scores):.2f} ({min(scores):g}–{max(scores):g})")
        rows.append(row)
    return headers, rows


def planted_gaps(results: Results, cases: list[Case]) -> tuple[list[str], list[list[Any]]]:
    """Are aspects written to be missing or weak flagged as not supported?

    False flags are counted on submissions written to the top mark on every criterion,
    where no aspect should be flagged.
    """

    headers = ["Condition", "Planted gaps", "Flagged as not supported", "Mark below the top level",
               "Aspects flagged in the all-strong submission"]
    rows = []
    for condition in results.conditions:
        found, lowered, strong_flags = [], [], []
        for case in cases:
            if case.planted is None or case.intended is None:
                continue
            maxima = {item["id"]: item["weight"] for item in criteria(load_rubric(case.rubric))}
            all_strong = not case.planted and all(score == maxima[c] for c, score in case.intended.items())
            for criterion, aspects in case.planted.items():
                row = results.get(case.id, "original", condition, criterion)
                if row is None:
                    continue
                status = {item["aspect_id"]: item["status"] for item in row.get("coverage") or []}
                found += [status.get(aspect, "missing") != "supported" for aspect in aspects] if status else []
                lowered.append(row["level_rank"] > 0)
            if all_strong:
                for criterion in case.intended:
                    row = results.get(case.id, "original", condition, criterion)
                    strong_flags += [item["status"] != "supported" for item in (row or {}).get("coverage") or []]
        rows.append([
            condition,
            len(found) if condition in EVIDENCE_CONDITIONS else "n/a",
            _pct(_share(found)) if condition in EVIDENCE_CONDITIONS else "n/a",
            _pct(_share(lowered)),
            _pct(_share(strong_flags)) if condition in EVIDENCE_CONDITIONS else "n/a",
        ])
    return headers, rows


# ---------------------------------------------------------------- output
def write_report(results_path: Path, out: Path, label_paths: list[Path] | None = None,
                 cases: list[Case] | None = None) -> Path:
    raw = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = Results(raw)
    out.mkdir(parents=True, exist_ok=True)
    sections: list[tuple[str, str, list[str], list[list[Any]]]] = []
    sections.append(("grounding", "Evidence and process (original submissions)", *grounding(results)))
    robust_headers, robust_rows, failures = robustness(results)
    injection = [0] + [i for i, h in enumerate(robust_headers) if h.startswith("Injection")]
    changes = [0] + [i for i, h in enumerate(robust_headers) if not h.startswith("Injection") and i]
    sections.append(("injection", "Prompt injection in the submission", [robust_headers[i] for i in injection],
                     [[row[i] for i in injection] for row in robust_rows]))
    sections.append(("controlled_changes", "Controlled changes to the content (metamorphic checks)",
                     [robust_headers[i] for i in changes], [[row[i] for i in changes] for row in robust_rows]))
    sections.append(("repeatability", "Repeatability", *repeatability(results)))
    sections.append(("cost", "Cost and latency per submission", *cost(results)))
    sections.append(("agreement", "Agreement between conditions", *agreement(results)))
    marked = [case for case in cases or [] if case.human]
    if marked:
        marks = {(case.id, c): {"marker": float(v)} for case in marked for c, v in (case.human or {}).items()}
        h, r, _, _ = human(results, marks)
        sections.append(("marker", "Agreement with the real marker", h, r))
        sections.append(("marker_totals", "Totals: real marker vs each condition", *totals(results, marked, "human")))
        for case in marked:
            sections.append((f"marker_{case.id}", f"{case.id}: real marker vs each condition, per criterion",
                             *per_criterion(results, case)))
    designed = [case for case in cases or [] if case.intended]
    if designed:
        h, r, _, _ = human(results, intended_marks(designed))
        sections.append(("intended", "Agreement with the intended marks (designed submissions)", h, r))
        sections.append(("totals", "Totals per submission: intended vs each condition", *totals(results, designed)))
        sections.append(("planted_gaps", "Planted gaps", *planted_gaps(results, designed)))
    if label_paths:
        h, r, rh, rr = human(results, read_labels(label_paths))
        sections.append(("human", "Agreement with human marks", h, r))
        sections.append(("raters", "Agreement between human markers", rh, rr))

    cases = sorted({r["case"] for r in results.rows})
    lines = [
        "# Evaluation results",
        "",
        f"{len(cases)} submissions · {len(results.rows)} criterion gradings · conditions: {', '.join(results.conditions)}",
        f"Models: {', '.join(sorted({str(r.get('model')) for r in results.rows if r.get('model')})) or '–'}",
        "",
    ]
    number = 0
    for name, title, headers, rows in sections:
        number += 1
        lines += [f"## {number}. {title}", "", _table(headers, rows), ""]
        _write_csv(out / f"{name}.csv", headers, rows)

    detail_headers = ["Check", "Condition", "Result key", "Detail"]
    detail = [[f["check"], f["condition"], f["key"],
               ", ".join(f"{k}={v}" for k, v in f.items() if k not in {"check", "condition", "key"})] for f in failures]
    _write_csv(out / "failed_checks.csv", detail_headers, detail)
    number += 1
    lines += [f"## {number}. Failed checks to inspect", ""]
    if detail:
        shown: dict[tuple[str, str], int] = defaultdict(int)
        examples = []
        for row in detail:
            shown[(row[0], row[1])] += 1
            if shown[(row[0], row[1])] <= _EXAMPLES:
                examples.append([row[0], row[1], f"`{row[2]}`", row[3]])
        lines += [f"{len(detail)} in total (all in failed_checks.csv); up to {_EXAMPLES} per check and condition:", "",
                  _table(detail_headers, examples)]
    else:
        lines.append("None.")
    errors = [r for r in results.rows if not r.get("ok")]
    if errors:
        number += 1
        lines += ["", f"## {number}. Gradings that failed", "",
                  _table(["Result key", "Error"], [[f"`{r['key']}`", r["error"][:200]] for r in errors])]
    summary = out / "summary.md"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
