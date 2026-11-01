# ADR 0008: Coverage records whether an aspect meets its standard, not only whether it is covered

Status: accepted, 2026-10-30 · changes how layer 3 of ADR 0006 decides an aspect's status

## Context

The evaluation (eval/results, commit 609019d) showed every evidence-based condition marking
generously. With the tool-based check, a deliberately weak "generic chatbot" proposal had
21 of 21 aspects supported, the same as the strongest proposal; only 14% of deliberately
planted gaps were flagged; and the group's real proposal scored 9.0 where the tutor gave 6.5.

The cause was the rule that filled the coverage matrix: one quote labelled *direct* made an
aspect *supported*. The model labels a quote direct when it is about the aspect, not when it
shows the aspect done well, while rubric levels differ precisely in quality ("measurable and
testable", "critically considered", "compelling"). With a full matrix the analytic cap never
applied.

## Decision

The evidence step answers two yes/no questions for every aspect, following checklist-based
evaluation (TICK, CheckEval): **addressed** (the submission covers it) and **meets_standard**
(the cited evidence shows it at the standard the aspect describes), each with a one-sentence
reason. The tool-based check asks once for missing answers before it finishes.

Each criterion has an **evidence standard**:

- `quality` (default): an aspect with supporting evidence is *supported* only if it also meets
  its standard; otherwise *partial*.
- `presence`: supporting evidence is enough, as before.

Default rule: a tutor's explicit choice wins; two-level met/not-met criteria and criteria worth
5% of the rubric or less use `presence`; every other criterion uses `quality`. A threshold on
weight alone was rejected: in most rubrics weights are similar (the ELEC5623 proposal rubric is
15–20% per criterion), so any threshold puts every criterion on the same side.

Answers can lower a status but never raise one: without verified evidence an aspect stays
missing whatever the model says. Missing answers fall back to the evidence-only status and are
counted. The coverage matrix, the analytic cap and the grade step are otherwise unchanged; the
grade step now sees each partial aspect's reason. Tutors see the answers in the evidence-check
timeline.

## Consequences

- Weak work that mentions every topic is now capped below the top level; strong work must
  show the quality the best level describes.
- The standard is stored with the criterion and used by grading and the evaluation; a control
  to change it in the rubric editor is not built yet.
- Prompt versions: `criterion-grade-fulltools-v2`, `-fulltext-v2`, `-coverage-v4` (v3/v5 after ADR 0009).
- Judging novelty against literature the submission does not cite remains outside what a
  submission-only check can do.
