# ADR 0006: The evidence step reads the whole submission; the mark comes only from verified evidence

Status: accepted, 2026-10-27 · changes what the evidence gate reads; the gate-then-grade design is kept

## Context

Each criterion used to see only the 12 passages retrieved for it. A criterion judged on the
whole work (structure, writing, referencing) saw fragments, and content phrased differently
from the rubric, or depending on a definition elsewhere, could be missed and marked absent.
University submissions (a 15–20 page report is roughly 8–15k tokens; with appendices rarely
above 30k) fit comfortably in current model context windows.

## Decision

Layers, each with one job:

1. **Read and find evidence** (model): the evidence step receives every paragraph of the
   submission, in order, with its id, page and paragraph number, and section headings. It
   returns verbatim quotes mapped to the criterion's aspects. It does not mark.
2. **Verify** (code): a quote is kept only if it is the submission's own text (typographic
   differences such as curly quotes, dashes and line breaks are tolerated; different words
   are not). A quote under the wrong paragraph id is moved to the paragraph it is in.
3. **Coverage** (code): which aspects are supported, partial, contradicted or missing is
   recomputed from verified evidence only; the model's own coverage claims are ignored.
4. **Mark** (model): the grade step sees the rubric, the verified evidence and coverage, and
   document facts computed by software (pages, words, outline, figure/table captions,
   reference-list entries). It does not see the full text.
5. **Rules** (code): no verified evidence → lowest level without a grade call; incomplete
   coverage on an analytic criterion → capped below the top level; the stored level is
   always the one the score falls in.

A submission that does not fit the model's context window (estimated, or reported by the
provider) is never truncated and never falls back to retrieval: it is routed to manual
marking with the reason shown. `MARKER_GRADING_CONTEXT=retrieval` keeps the old behaviour
for evaluation comparisons only.

The submission text is the first part of every evidence prompt and is identical across a
submission's criteria; the first criterion's evidence call is sent alone so providers that
cache prompt prefixes can reuse it for the others.

## Consequences

- Evidence-step input grows from ~3–4k to roughly the submission length per criterion;
  prefix caching reduces the cost where the provider supports it.
- Figures and images are still not read (text extraction only).
- Planned next: re-check aspects judged missing with retrieval as a second opinion; measure
  full-text against retrieval with the evaluation harness.
