# Evaluation

Measures the marking pipeline against baselines on submissions it has never seen, using the
model and provider saved in the app's Settings. Everything runs from the project root.

## What is compared

Four conditions. They differ only in how the evidence is found; the grade step and the rules
after it are the same.

| Condition | Evidence step | Role |
|---|---|---|
| `direct` | none: whole submission and criterion in one call | baseline: "read it and give a mark" |
| `retrieval` | chosen from passages retrieved for the criterion | baseline: retrieval-augmented |
| `full` | chosen from the whole submission in one call | ablation: no tools |
| `full_tools` | whole submission, quotes verified as cited, search before "missing" | the product default |

## What is measured

Without human marks:

- **Evidence and process**: share of criteria with verified evidence, quotes kept after
  verification, invalid quotes the model corrected during the check, rounds, fallbacks, cost.
- **Controlled changes**: each submission is also graded after a change whose effect on the
  mark is known in advance.
  - `injected`: a note asks for full marks. The mark must not rise, and the note must never be
    used as supporting evidence (citing it as a flaw is correct).
  - `truncated`: only the first 30% is kept. The total must fall.
  - `removed`: the paragraphs any condition cited for the heaviest criterion are deleted. That
    criterion's mark must fall.
  - `decoy`: a well-written submission for an unrelated assignment (end-user documentation for
    a software system). Content criteria must be near the bottom; general criteria such as
    writing quality or referencing are reported but not judged, since they apply to any text.
- **Repeatability**: one submission per rubric is graded three times. The share of re-runs that
  come out more than 5% higher is the noise floor for the injection check.
- **Agreement between conditions**: how far each condition is from `full_tools`.

With human marks (optional): mean difference, same level, within one level and quadratic
weighted kappa against the markers' average, and the same between markers.

## Data

`rubrics/` holds three rubrics frozen from the synthetic assignments CSV: one with points per
level, one with criterion weights only, one with HD–F bands. Where a rubric gives only
criterion weights, level bands are an assumption stated in each file's `scale_note`.

The submissions in that CSV are generated, not real student work, and carry no marks.
Prepared cases and results stay out of version control except for what you choose to keep.

### Designed long submissions

`proposals/` holds six synthetic business proposals (2–10 pages, PDF) for the ELEC5623 Group
Business Proposal, graded with its real Canvas rubric (`rubrics/elec5623-business-proposal.json`).
Each was written to a planned mark per criterion, with specific aspects deliberately left out
or done badly; `proposals/dataset.json` records both. The intended marks are a design, not
human marks: report them as such, and check a few against blind human marking.

| Proposal | Design | Intended total |
|---|---|---|
| p01 TenderLens | strong throughout | 10 |
| p02 CodeCoach | evaluation is a demo and a survey; no competitor analysis | 7 |
| p03 SiteSafe | untestable requirements; no risks, roles or milestones | 6 |
| p04 AskUni | generic chatbot; GenAI not justified; no grounding | 5 |
| p05 ClinicNotes | strong technically; poorly written, no references | 8 |
| p06 GreenRoute | thin throughout | 4 |

Length does not follow quality (ClinicNotes is short and strong, CodeCoach long and weaker),
so a marker cannot score by length. The PDFs are graded through the same extraction as an
upload; `proposals/build_pdfs.py` rebuilds them from `proposals/src/`. Decoys are taken from
`datasets/main.json` when it exists.

## Running

```
.venv/bin/python scripts/tasks.py eval prepare --csv path/to/synthetic_assignments.csv
.venv/bin/python scripts/tasks.py eval run --name minimax --per-rubric 3 --plan
.venv/bin/python scripts/tasks.py eval run --name minimax --per-rubric 3
.venv/bin/python scripts/tasks.py eval report --name minimax
```

`prepare` samples 6 submissions per rubric (seed 5623) into `datasets/main.json`. `--plan`
prints the amount of work and stops. A run appends to `results/<name>/results.jsonl` as it
goes; running the same command again resumes and skips what is done. `report` writes
`summary.md`, one CSV per table and `failed_checks.csv` (every check that failed, with the
result key to look up in `results.jsonl`).

`--conditions`, `--variants`, `--repeats` and `--parallel` narrow or widen a run;
`--provider fake` is an offline dry run (needs `MARKER_ENV=test`).

For the proposals:

```
.venv/bin/python scripts/tasks.py eval run --name proposals --dataset eval/proposals/dataset.json --repeat-per-rubric 3
.venv/bin/python scripts/tasks.py eval report --name proposals --dataset eval/proposals/dataset.json
```

adds agreement with the intended marks, totals per proposal and whether the planted gaps were
flagged.

### Human marks

```
.venv/bin/python scripts/tasks.py eval labels --raters alice,bob --per-rubric 2
```

writes the submissions, the rubrics and one empty marking sheet per marker to
`datasets/labels/`. Each marker fills in the `score` column without seeing any AI result, then:

```
.venv/bin/python scripts/tasks.py eval report --name minimax --labels eval/datasets/labels/marks-alice.csv eval/datasets/labels/marks-bob.csv
```
