# Evaluation evidence

Every result behind the report's evaluation, one folder per run. Each folder holds the raw
gradings (`results.jsonl`), the tables (`*.csv`) and a `summary.md` written from them by
`python -m eval report` (harness runs) or `python -m eval.cohort.run_report` (the product run).
Model throughout: MiniMax-M3.1-Flash. Money is at the provider's list prices (`eval/prices.py`).

## What each folder is

| Folder | Code | Dataset | Gradings | Role in the report |
|---|---|---|---|---|
| `proposals/` | 609019d, before the fix | 6 designed ELEC5623 proposals with intended marks and 28 planted gaps | 744 | baseline for the before/after comparison |
| `proposals-v4/` | c1ef63d | same 6 proposals | 744 | main comparison of the four conditions; planted gaps; controlled changes |
| `minimax-v2/` | 609019d, before the fix | 9 submissions from 3 other rubrics (CSV cases) | 820 | before/after on other rubrics |
| `minimax-v4/` | c1ef63d | same 9 submissions | 820 | the fix generalises across rubrics |
| `real*/` | both | the group's own proposal and the tutor's marks | 196 / 124 | held-out real case; private, kept only locally (git-ignored) |
| `cohort-run/` | 94b1802 | 100-submission cohort marked through the product (batch upload, worker, review) | 600 | cost, time and reliability at batch scale |

Conditions in the harness runs: `direct` (whole submission, one call per criterion: the
"just ask the model" baseline), `retrieval` (evidence chosen from retrieved passages),
`full` (evidence chosen from the whole text in one call, no tools: ablation) and
`full_tools` (the product: an agent cites and searches with tools, every quote verified).

## Evidence by claim

| Claim | Evidence | File |
|---|---|---|
| The tool-based agent only ever grades from real text | 100% of quotes kept after verification; invalid quotes corrected inside the loop (11 of 260 on the proposals; 11 of 4,015 in the product run) | `proposals-v4/grounding.csv`, `cohort-run/summary.md` |
| Accuracy is on a par with the direct baseline, not better | QWK vs intended marks: direct 0.77 (0.54–0.89), full_tools 0.67 (0.41–0.83), full 0.65, retrieval 0.33; intervals overlap | `proposals-v4/intended.csv` |
| The fix made marking stricter where it should | planted gaps flagged by full_tools: 14% (6–31%) before, 86% (69–94%) after; mean mark 80% → 74% on the proposals (intended 67%) and 85% → 82% on the other rubrics | `proposals*/planted_gaps.csv`, `*/grounding.csv` |
| …without punishing strong work much | all-strong proposal: 10 → 9.5 (one material deduction: no architecture figure) | `proposals-v4/totals.csv`, `planted_gaps.csv` |
| More robust to prompt injection than the baseline | mark not raised: full_tools 92% / 88%, direct 83% / 83% (proposals / other rubrics) | `*-v4/injection.csv` |
| More repeatable on the proposals | same level on every re-run: full_tools 72%, direct 61%; mean spread 4% vs 5% | `proposals-v4/repeatability.csv` |
| Cost and speed are the price | per submission: full_tools US$0.0148, 31 s per criterion; direct US$0.0038, 5 s | `proposals-v4/cost.csv` |
| At batch scale the cost is low and predictable | 100 submissions US$1.65; per submission mean 0.0165, 95th percentile 0.0191; 61.5% of input read from cache | `cohort-run/summary.md` |
| …and reliable | 600 of 600 criteria graded; no fallback to a single read; one job retried after a rate-limit error | `cohort-run/summary.md` |
| Throughput is bounded by the provider plan, not the system | 75 submissions in the first hour; seven pauses (2.1 h in all) under the MiniMax Token Plan rate limit | `cohort-run/summary.md` |

## Failure cases and limitations (for section 8)

- **The real proposal is still marked high.** Tutor 6.5; full_tools 9.0–10.0 over three
  runs, direct 9.0–9.5, full 8.0. About 2–2.5 of the 3.5 points come from judgements outside
  the submission and the rubric text (novelty against published work, research
  alternatives, how many references are enough); hedged wording that should have been
  caught accounts for another 0.5. (`real-v4/summary.md`, local only)
- **Removing the cited evidence rarely lowers full_tools' mark** on the proposals (33% vs
  100% for direct; 67% on the other rubrics): the agent finds other passages.
- **Level flips on re-runs** on the other rubrics: full_tools 50% same level, marks sitting
  on the boundary between the top two levels.
- **The designed proposals confound length with quality** (Spearman 0.94 between words and
  intended mark), so they cannot show length-independence; on the other rubrics no
  condition follows length (full_tools ρ = -0.08).
- **The product run's cohort was written by a template generator** that adds the same
  proposal-style filler to every submission, including off-topic and incomplete ones, so
  its agreement figures (QWK 0.32, AI total 7.49 vs specified 6.41) describe the generator
  as much as the marker; it is used for cost, time and reliability.
- **Writing quality is under-detected**: the five "strong content, poor writing" cohort
  submissions all received 1.0 rather than 0.5 for communication.
- **Intended marks are a design, not human marks**; only one submission has a tutor's
  marks. Blind marking by people would be the next step.

## Reproducing

```
.venv/bin/python scripts/tasks.py eval run --name proposals-v4 --dataset eval/proposals/dataset.json --repeat-per-rubric 3
.venv/bin/python scripts/tasks.py eval run --name minimax-v4 --per-rubric 3
.venv/bin/python scripts/tasks.py eval report --name proposals-v4 --dataset eval/proposals/dataset.json
.venv/bin/python scripts/tasks.py eval report --name minimax-v4
.venv/bin/python -m eval.cohort.run_report --batch <batch id>
```

Model output varies between runs, so re-running reproduces the procedure and the size of the
effects, not every mark. The cohort's submissions are rebuilt with
`python -m eval.cohort.local_generate --only <ids>` from `eval/cohort/specs.json`; their
file names map to cohort ids through `eval/cohort/sid_map.csv`.
