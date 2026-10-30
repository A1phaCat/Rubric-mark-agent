"""Evaluation commands. Run from the project root:

    .venv/bin/python scripts/tasks.py eval prepare --csv synthetic_assignments.csv
    .venv/bin/python scripts/tasks.py eval run --name minimax-v1
    .venv/bin/python scripts/tasks.py eval report --name minimax-v1
    .venv/bin/python scripts/tasks.py eval labels --raters darin,yutong
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

HERE = Path(__file__).parent
DATASET = HERE / "datasets" / "main.json"
RESULTS = HERE / "results"


def _list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _settings(provider: str | None, out: Path):
    from app.config import settings as configured
    from app.db.session import SessionLocal
    from app.services.settings_service import load_ai_settings

    runtime = configured.model_copy(deep=True)
    with SessionLocal() as session:
        load_ai_settings(session, runtime)  # the provider, model and key saved in Settings
    if provider:
        runtime.llm = provider
    # Retrieval vectors for evaluation copies stay out of the application's data folder.
    runtime.data_dir = out / "cache"
    return runtime


def main() -> None:
    from . import dataset, labels, report, runner

    parser = argparse.ArgumentParser(prog="eval")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="sample cases from the assignments CSV")
    prepare.add_argument("--csv", type=Path, required=True)
    prepare.add_argument("--rubrics", type=_list, default=dataset.rubric_keys(csv_only=True))
    prepare.add_argument("--per-rubric", type=int, default=6)
    prepare.add_argument("--min-chars", type=int, default=6000)
    prepare.add_argument("--seed", type=int, default=5623)
    prepare.add_argument("--out", type=Path, default=DATASET)

    run = commands.add_parser("run", help="grade the cases under each condition and variant")
    run.add_argument("--name", required=True, help="folder under eval/results")
    run.add_argument("--dataset", type=Path, default=DATASET)
    run.add_argument("--conditions", type=_list, default=list(runner.CONDITIONS))
    run.add_argument("--variants", type=_list, default=list(runner.VARIANTS))
    run.add_argument("--per-rubric", type=int, default=0, help="only the first N cases of each rubric (0 = all)")
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--repeat-per-rubric", type=int, default=1, help="cases per rubric whose original is graded --repeats times")
    run.add_argument("--removal-criteria", type=int, default=1, help="heaviest criteria per case to remove evidence for")
    run.add_argument("--parallel", type=int, default=6)
    run.add_argument("--provider", help="override the saved provider, e.g. fake for a dry run")
    run.add_argument("--plan", action="store_true", help="print how much work the run is, then stop")

    show = commands.add_parser("report", help="write tables and summary.md for a run")
    show.add_argument("--name", required=True)
    show.add_argument("--labels", type=Path, nargs="*", default=[])
    show.add_argument("--dataset", type=Path, help="adds intended-mark and planted-gap tables for designed cases")

    sheets = commands.add_parser("labels", help="export blind marking sheets for human markers")
    sheets.add_argument("--dataset", type=Path, default=DATASET)
    sheets.add_argument("--raters", type=_list, required=True)
    sheets.add_argument("--per-rubric", type=int, default=0)
    sheets.add_argument("--out", type=Path, default=HERE / "datasets" / "labels")

    args = parser.parse_args()
    if args.command == "prepare":
        data = dataset.prepare(args.csv, args.out, keys=args.rubrics, per_rubric=args.per_rubric,
                               seed=args.seed, min_chars=args.min_chars)
        print(f"{len(data['cases'])} cases from {len(args.rubrics)} rubrics → {args.out}")
    elif args.command == "run":
        out = RESULTS / args.name
        out.mkdir(parents=True, exist_ok=True)
        cases = dataset.load_cases(args.dataset, args.per_rubric)
        units = runner.plan(cases, decoys=dataset.load_decoys(args.dataset), conditions=args.conditions,
                            variant_names=args.variants, repeats=args.repeats,
                            repeat_per_rubric=args.repeat_per_rubric)
        gradings = sum(len(unit.criteria) for unit in units)
        removal = len(cases) * args.removal_criteria * len(args.conditions) if "removed" in args.variants else 0
        print(f"{len(cases)} cases · {len(units)} graded versions · {gradings} criterion gradings"
              f" + up to {removal} after evidence removal")
        if args.plan:
            return
        settings = _settings(args.provider, out)
        print(f"provider {settings.llm} · model {settings.ai_model}")
        results = out / "results.jsonl"
        engine = runner.Runner(settings, results, parallel=args.parallel)
        asyncio.run(engine.run(units))
        if "removed" in args.variants:
            later = runner.removal_plan(cases, args.conditions, runner.read_results(results), args.removal_criteria)
            engine = runner.Runner(settings, results, parallel=args.parallel)
            asyncio.run(engine.run(later))
        print(f"results → {results}")
    elif args.command == "report":
        out = RESULTS / args.name
        cases = dataset.load_cases(args.dataset) if args.dataset else None
        summary = report.write_report(out / "results.jsonl", out, args.labels, cases)
        print(f"summary → {summary}")
    elif args.command == "labels":
        cases = dataset.load_cases(args.dataset, args.per_rubric)
        for path in labels.export(cases, args.out, args.raters):
            print(f"marking sheet → {path}")


if __name__ == "__main__":
    main()
