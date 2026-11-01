# ADR 0009: The grade step lists deductions before it chooses a level

Status: accepted, 2026-10-30 · follows ADR 0008

## Context

After ADR 0008 the group's real proposal still received full marks on all six criteria
(tutor: 6.5 of 10). Every one of its 21 aspects was answered "meets the standard": the same
model that found the evidence was asked to confirm it, and it confirmed it. A long, detailed
submission that touches every topic read as excellent, so length and confident wording were
being marked as quality.

Two constraints shaped the fix. It has to work for any rubric, because the evaluation runs
several rubrics and assignments; wording tuned to one rubric would not carry over. And the
real proposal is held out: nothing was tuned against it.

## Decision

Marking moves from "is there support for the best level" to "what keeps this from the best
level", as human markers justify a mark:

1. **Evidence step**: cites, for each aspect, the strongest support *and* the weakest or most
   limited passage (vague or hedged statements, claims without support, parts left undone),
   so the grade step sees both sides.
2. **Grade step**: before choosing a level it returns `deductions`, each with the aspect, a
   severity (`minor` or `material`), the issue and the evidence (a bracket such as `p.2 ¶3`
   shown to it, or `absent`). The prompt compares the evidence with the best level's
   description and the level below, and states generic rules only: length and detail are not
   quality, a list is not analysis, a claim is not a demonstration, a plan that names
   possibilities has not decided.
3. **Code**: drops deductions that name an unknown aspect, an unknown severity, or evidence
   the grade step was not shown. Under the `quality` standard any remaining material
   deduction holds the mark below the best level (`capped: "deduction"`); the coverage cap of
   ADR 0006 still applies first (`capped: "coverage"`). Under the `presence` standard
   deductions are shown but do not cap.

Tutors see the deductions and whether a cap applied in the evidence-check timeline. The
evaluation records them and reports how often a material deduction named a planted gap and
how many fell on the submission written to be strong throughout (false deductions).

## Consequences

- The best level has to be earned: work with a material shortfall cannot reach it, whatever
  its length.
- Strong work can still be held down by an over-strict model; the all-strong designed
  proposal is the check for that, and the tutor can always override.
- Course-specific expectations that the rubric text does not state (what a tutor counts as
  "critical") are outside this change; they belong in optional marker notes per criterion.
- Prompt versions: `criterion-grade-fulltools-v3`, `-fulltext-v3`, `-coverage-v5`.
