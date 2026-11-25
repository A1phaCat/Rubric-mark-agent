# ADR 0007: The evidence step is a bounded tool-using check over the whole submission

Status: accepted, 2026-10-27 · changes how layer 1 of ADR 0006 runs; layers 2–5 are unchanged

## Context

With the whole submission in one call (ADR 0006), the evidence step had no way to learn that
a quote was wrong until after it had answered, and it could report an aspect missing without
looking for it in other words. On the first real batch most criteria came back with partial
coverage while the model still reported high confidence. Tutors also had no way to see how
the evidence had been found.

## Decision

`MARKER_GRADING_CONTEXT=full_tools` (the default) runs the evidence step as a short check
with three read-only tools:

- **cite** records a quote and verifies it against the submission at once (same rules as
  layer 2: typography tolerated, different words rejected, wrong paragraph id corrected).
  The model is told immediately when a quote is invalid and can correct it.
- **search** finds paragraphs by keyword (BM25 plus exact phrase matches; no embeddings).
- **finish** ends the check and names any aspect not addressed.

Rules the code enforces:

- The model always receives the complete submission. Search helps it look again; it never
  replaces reading.
- An aspect can be finished as missing only after a search for it. The first early finish
  is sent back once with the aspects to search; the next one is accepted.
- At most `MARKER_AGENT_MAX_ROUNDS` (4) model turns, plus one if it was sent back to search.
  At the limit the quotes already verified are kept.
- The check's output is the same evidence list the one-shot step produced, so verification,
  coverage, the grade step and the marking rules are unchanged.

The submission text is the system message and is identical for every criterion and turn, so
providers that cache prompt prefixes reuse it; the first criterion's first turn still goes
alone before the others start.

**Fallback.** If the provider has no tool calling, rejects the request (400/404/405/422), cuts
the answer off, or the check ends without any evidence and without finishing, the criterion
is read again in one pass (ADR 0006). Wrong keys, rate limits and over-long submissions are
not hidden by the fallback.

**Record.** Each step (read, model turn, tool call and its outcome, send-back, limit,
fallback) is stored with the AI result and shown to tutors as a collapsible timeline on the
review screen. It is never part of the student report. Every provider call, with input,
output and cached tokens, is written to `llm_calls`.

## Consequences

- An evidence check is two to four provider calls per criterion instead of one; most of the
  input after the first turn is read from the provider cache.
- Invented quotes are corrected during the check instead of being dropped afterwards, and
  "missing" means "not found after a search".
- `MARKER_GRADING_CONTEXT=full` and `retrieval` remain for comparisons; prompt versions are
  `criterion-grade-fulltools-v1`, `-fulltext-v1` and `-coverage-v3`.
- Not yet done: comparing `full_tools` with `full` on the same batches with the evaluation
  harness; a navigation-only variant for submissions too long to read whole.
