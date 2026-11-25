"""Report on a batch of the cohort marked through the product itself.

Reads the app's database (standard library only, so it runs wherever the database is) and
writes, for one batch, what it cost, how long it took, how reliably it ran, and how the marks
compare with the cohort's specification:

    python -m eval.cohort.run_report --batch <batch id> [--db data/db/marker.sqlite3] [--out eval/results/cohort-run]

Outputs: summary.md, submissions.csv (one row per submission) and criteria.csv (one row per
criterion graded). Submissions are matched to their specification through sid_map.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.metrics import adjacent_agreement, level_agreement, quadratic_weighted_kappa, spearman, wilson_interval
from eval.prices import dollars

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
RUBRIC = ROOT / "eval" / "rubrics" / "elec5623-business-proposal.json"
GAP_SECONDS = 120


def _percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * (len(ordered) - 1)))]


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return "\n".join(lines + ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows])


def _criteria(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """The batch's criteria in rubric order, each with its specification id (c1…c6) and levels."""

    reference = json.loads(RUBRIC.read_text(encoding="utf-8"))["criteria"]
    names = {item["name"].strip().lower(): item["id"] for item in reference}
    result = []
    for position, item in enumerate(snapshot["criteria"]):
        key = names.get(str(item.get("name", "")).strip().lower(), f"c{position + 1}")
        points = sorted({float(level["points"]) for level in item.get("levels", [])}, reverse=True)
        result.append({"id": item["id"], "key": key, "name": item["name"], "points": points})
    return result


def _rank(points: list[float], score: float) -> int:
    return min(range(len(points)), key=lambda index: abs(points[index] - score))


def collect(db: Path, batch: str) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    row = connection.execute(
        "select name, model_provider, model_name, rubric_snapshot_json, started_at from batches where id = ?", (batch,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"no batch {batch} in {db}")
    name, provider, model, snapshot, started = row
    criteria = _criteria(json.loads(snapshot))
    submissions = {sid: {"id": sid_id, "sid": sid, "words": words, "status": status}
                   for sid_id, sid, words, status in connection.execute(
                       "select id, sid, word_count, status from submissions where batch_id = ?", (batch,))}
    by_id = {item["id"]: item for item in submissions.values()}
    marks = "?," * len(by_id)
    calls = connection.execute(
        f"select submission_id, purpose, model, input_tokens, cached_tokens, output_tokens, latency_ms, created_at "
        f"from llm_calls where submission_id in ({marks[:-1]})", list(by_id)).fetchall()
    results = connection.execute(
        "select s.sid, a.criterion_id, a.score, a.level, a.confidence, a.minor_json, a.trace_json "
        "from ai_results a join submissions s on s.id = a.submission_id where s.batch_id = ?", (batch,)).fetchall()
    jobs = connection.execute(
        "select status, attempts, last_error from jobs where batch_id = ?", (batch,)).fetchall()
    return {"name": name, "provider": provider, "model": model, "started": started, "criteria": criteria,
            "submissions": submissions, "by_id": by_id, "calls": calls, "results": results, "jobs": jobs}


def build(data: dict[str, Any], specs: dict[str, dict[str, Any]], cases: dict[str, str]) -> dict[str, Any]:
    criteria = {item["id"]: item for item in data["criteria"]}
    usage: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "input": 0, "cached": 0, "output": 0,
                                                           "first": None, "last": None})
    times = []
    for submission_id, _purpose, model, input_tokens, cached, output, _latency, created in data["calls"]:
        sid = data["by_id"][submission_id]["sid"]
        entry = usage[sid]
        entry["calls"] += 1
        entry["input"] += input_tokens
        entry["cached"] += cached
        entry["output"] += output
        entry["model"] = model
        moment = _when(created)
        times.append(moment)
        entry["first"] = moment if entry["first"] is None or moment < entry["first"] else entry["first"]
        entry["last"] = moment if entry["last"] is None or moment > entry["last"] else entry["last"]
    marks: dict[str, dict[str, float]] = defaultdict(dict)
    rows = []
    for sid, criterion_id, score, level, confidence, minor, trace in data["results"]:
        criterion = criteria[criterion_id]
        steps = json.loads(trace or "[]")
        details = json.loads(minor or "{}") if (minor or "").startswith("{") else {}
        case = cases.get(sid, "")
        spec = specs.get(case, {})
        marks[sid][criterion["key"]] = float(score)
        rows.append({
            "sid": sid, "case": case, "type": spec.get("type", ""), "criterion": criterion["key"],
            "intended": (spec.get("intended") or {}).get(criterion["key"], ""), "ai": score, "level": level,
            "rounds": sum(step.get("kind") == "model" for step in steps),
            "verified_quotes": sum(step.get("tool") == "cite" and step.get("outcome") in ("valid", "relocated")
                                   for step in steps),
            "invalid_quotes": sum(step.get("tool") == "cite" and step.get("outcome") == "invalid" for step in steps),
            "fallback": any(step.get("kind") == "fallback" for step in steps),
            "material_deductions": sum(item.get("severity") == "material" for item in details.get("deductions") or []),
            "capped": details.get("capped") or "", "confidence": confidence,
        })
    submissions = []
    for sid, item in sorted(data["submissions"].items()):
        entry, case = usage.get(sid), cases.get(sid, "")
        spec = specs.get(case, {})
        intended = spec.get("intended") or {}
        cost = dollars(entry.get("model"), entry["input"], entry["cached"], entry["output"]) if entry else None
        submissions.append({
            "sid": sid, "case": case, "type": spec.get("type", "unspecified"), "source": spec.get("source", ""),
            "length": spec.get("length", ""),
            "words": item["words"], "status": item["status"],
            **{f"intended_{c['key']}": intended.get(c["key"], "") for c in data["criteria"]},
            "intended_total": sum(intended.values()) if intended else "",
            **{f"ai_{c['key']}": marks[sid].get(c["key"], "") for c in data["criteria"]},
            "ai_total": sum(marks[sid].values()) if marks[sid] else "",
            "calls": entry["calls"] if entry else 0, "input_tokens": entry["input"] if entry else 0,
            "cached_tokens": entry["cached"] if entry else 0, "output_tokens": entry["output"] if entry else 0,
            "cost_usd": round(cost, 5) if cost is not None else "",
            "seconds": round((entry["last"] - entry["first"]).total_seconds()) if entry else "",
            "first_call": entry["first"].isoformat() if entry else "", "last_call": entry["last"].isoformat() if entry else "",
        })
    return {"submissions": submissions, "criteria": rows, "times": sorted(times)}


def _accuracy(rows: list[dict[str, Any]], criteria: list[dict[str, Any]], label: str) -> list[Any]:
    points = {c["key"]: c["points"] for c in criteria}
    pairs = [(r, c["key"]) for r in rows for c in criteria if r[f"intended_{c['key']}"] != "" and r[f"ai_{c['key']}"] != ""]
    if not pairs:
        return [label, 0, "–", "–", "–", "–", "–", "–", "–"]
    expected = [_rank(points[k], float(r[f"intended_{k}"])) for r, k in pairs]
    actual = [_rank(points[k], float(r[f"ai_{k}"])) for r, k in pairs]
    bias = statistics.mean((float(r[f"ai_{k}"]) - float(r[f"intended_{k}"])) / points[k][0] for r, k in pairs)
    error = statistics.mean(abs(float(r[f"ai_{k}"]) - float(r[f"intended_{k}"])) / points[k][0] for r, k in pairs)
    size = max(len(p) for p in points.values())
    return [label, len(rows), f"{statistics.mean(r['intended_total'] for r in rows):.2f}",
            f"{statistics.mean(r['ai_total'] for r in rows):.2f}", f"{error * 100:.0f}%", f"{bias * 100:+.0f}%",
            f"{level_agreement(expected, actual) * 100:.0f}%", f"{adjacent_agreement(expected, actual) * 100:.0f}%",
            f"{quadratic_weighted_kappa(expected, actual, size):.2f}"]


def summary(data: dict[str, Any], built: dict[str, Any], batch: str) -> str:
    subs = [s for s in built["submissions"] if s["calls"]]
    costs = [s["cost_usd"] for s in subs if s["cost_usd"] != ""]
    seconds = [s["seconds"] for s in subs]
    times = built["times"]
    hours = (times[-1] - times[0]).total_seconds() / 3600 if times else 0
    gaps = [(a, (b - a).total_seconds()) for a, b in zip(times, times[1:]) if (b - a).total_seconds() > GAP_SECONDS]
    finished = sorted(_when(s["last_call"]) for s in subs)
    milestones = [(k, (finished[k - 1] - times[0]).total_seconds() / 60) for k in (25, 50, 75, len(finished))
                  if k <= len(finished)]
    criteria_rows = built["criteria"]
    input_total = sum(s["input_tokens"] for s in subs)
    cached_total = sum(s["cached_tokens"] for s in subs)
    cites = sum(r["verified_quotes"] for r in criteria_rows) + sum(r["invalid_quotes"] for r in criteria_rows)
    jobs = Counter(status for status, _, _ in data["jobs"])
    errors = Counter((error or "")[:120] for status, _, error in data["jobs"] if error)
    lines = [
        "# Marking run through the product",
        "",
        f"Batch `{batch}` · {data['name']} · {data['provider']} / {data['model']} · started {data['started']}",
        f"{len(subs)} submissions · {len(criteria_rows)} criteria graded",
        "",
        "## Cost (provider list prices, `eval/prices.py`)",
        "",
        _table(["Measure", "Value"], [
            ["Total", f"US$ {sum(costs):.3f}"],
            ["Per submission: mean / median / 95th percentile", f"US$ {statistics.mean(costs):.4f} / "
             f"{_percentile(costs, .5):.4f} / {_percentile(costs, .95):.4f}"],
            ["Per submission: range", f"US$ {min(costs):.4f}–{max(costs):.4f}"],
            ["Input tokens per submission (mean)", f"{statistics.mean(s['input_tokens'] for s in subs):,.0f}"],
            ["Read from the provider cache", f"{cached_total / input_total * 100:.1f}%"],
            ["Output tokens per submission (mean)", f"{statistics.mean(s['output_tokens'] for s in subs):,.0f}"],
            ["Model calls per submission (mean)", f"{statistics.mean(s['calls'] for s in subs):.1f}"],
            ["Words per submission: mean (range)", f"{statistics.mean(s['words'] for s in subs):,.0f} "
             f"({min(s['words'] for s in subs):,}–{max(s['words'] for s in subs):,})"],
        ]),
        "",
        "## Time",
        "",
        _table(["Measure", "Value"], [
            ["First to last model call", f"{hours:.2f} h"],
            *[[f"{k} submissions finished after", f"{minutes:.1f} min"] for k, minutes in milestones],
            ["Per submission, first to last call: median / 95th percentile",
             f"{_percentile(seconds, .5):.0f} s / {_percentile(seconds, .95):.0f} s"],
            [f"Pauses longer than {GAP_SECONDS} s with no model call", f"{len(gaps)}, {sum(g for _, g in gaps) / 3600:.2f} h in all"],
        ]),
        "",
        "## Reliability",
        "",
        _table(["Measure", "Value"], [
            ["Criteria graded", f"{len(criteria_rows)} of {len(data['submissions']) * len(data['criteria'])}"],
            ["Tool-based evidence check fell back to a single read", f"{sum(r['fallback'] for r in criteria_rows)}"],
            ["Agent rounds per criterion (mean)", f"{statistics.mean(r['rounds'] for r in criteria_rows):.2f}"],
            ["Quotes cited / rejected by verification and corrected", f"{cites} / {sum(r['invalid_quotes'] for r in criteria_rows)}"],
            ["Criteria with a material deduction", f"{sum(r['material_deductions'] > 0 for r in criteria_rows) / len(criteria_rows) * 100:.0f}%"],
            ["Grading jobs by final status", ", ".join(f"{k}: {v}" for k, v in sorted(jobs.items()))],
            *[[f"Job error ({count}×)", f"`{text}`"] for text, count in errors.most_common(3)],
        ]),
        "",
    ]
    specified = [s for s in subs if s["intended_total"] != "" and s["ai_total"] != ""]
    if specified:
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in specified:
            by_type[item["type"]].append(item)
        headers = ["Submissions", "n", "Specified total", "AI total", "Mean difference", "Bias", "Same level",
                   "Within one level", "QWK"]
        rows = [_accuracy(specified, data["criteria"], "all")]
        rows += [_accuracy(items, data["criteria"], kind) for kind, items in sorted(by_type.items())]
        normal = by_type.get("normal", [])
        duplicates = [(s, next((o for o in specified if o["case"] == s["source"]), None))
                      for s in by_type.get("near_duplicate", [])]
        lines += ["## Agreement with the specification", "",
                  "The cohort was written by a template generator (`eval/cohort/local_generate.py`) that adds the "
                  "same proposal-style filler paragraphs to every submission, including off-topic and incomplete "
                  "ones, so these figures describe the generator as much as the marker.", "",
                  _table(headers, rows), ""]
        if len(normal) >= 3:
            words = [s["words"] for s in normal]
            rho_spec = spearman(words, [s["intended_total"] for s in normal])
            rho_ai = spearman(words, [s["ai_total"] for s in normal])
            rho_gap = spearman(words, [s["ai_total"] - s["intended_total"] for s in normal])
            lines += ["Length (normal submissions): Spearman ρ between words and the specified total "
                      f"{rho_spec:.2f}, the AI total {rho_ai:.2f}, and the AI's excess over the specification "
                      f"{rho_gap:.2f} (n = {len(normal)}).", ""]
        pairs = [(a, b) for a, b in duplicates if b is not None]
        if pairs:
            same = sum(a["ai_total"] == b["ai_total"] for a, b in pairs)
            interval = wilson_interval(same, len(pairs))
            lines += [f"Near-duplicates: {same} of {len(pairs)} paraphrases got the same total as their source "
                      f"(95% interval {interval[0] * 100:.0f}–{interval[1] * 100:.0f}%); differences: "
                      + ", ".join(f"{a['case']} vs {b['case']} {a['ai_total'] - b['ai_total']:+g}" for a, b in pairs) + ".", ""]
    if gaps:
        lines += ["## Pauses", "", _table(["Started (UTC)", "Minutes"],
                                         [[str(start)[:19], f"{seconds / 60:.1f}"] for start, seconds in gaps]), ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch", required=True)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "db" / "marker.sqlite3")
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results" / "cohort-run")
    args = parser.parse_args()
    specs = {item["id"]: item for item in json.loads((HERE / "specs.json").read_text(encoding="utf-8"))}
    with (HERE / "sid_map.csv").open(encoding="utf-8") as handle:
        cases = {row["sid"]: row["case"] for row in csv.DictReader(handle)}
    data = collect(args.db, args.batch)
    built = build(data, specs, cases)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("submissions", built["submissions"]), ("criteria", built["criteria"])):
        with (args.out / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (args.out / "summary.md").write_text(summary(data, built, args.batch) + "\n", encoding="utf-8")
    print(f"{len(built['submissions'])} submissions → {args.out}")


if __name__ == "__main__":
    main()
