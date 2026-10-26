# ADR 0005: Sample data lives in the database, not in fixtures

Status: accepted, 2026-10-20 · supersedes the mock/fixture parts of ADR 0001 and the review's demo-data plan

## Decision

- The frontend has no mock mode. Every page renders data returned by `/api/v1`, and every API response is
  computed from database rows. `fixtures/demo/`, `mock-adapter.js`, `FixtureStore`, `is_mock` and the
  `?mocks=1` mode are removed; an architecture test keeps them out.
- Demonstration data is loaded by `python -m app.sample.seed` as ordinary rows marked `is_sample`. The
  seeder uses the real services: rubrics via `RubricUseCases`, files via `store_upload` + `apply_extraction`,
  tutor edits/confirmations via `ReviewUseCases`, finalisation via `BatchUseCases`. Only AI grading is
  replayed from recorded results (`provider="sample"`), and every recorded evidence quote must be found in
  the extracted text or seeding fails.
- At most three batches are pinned (`pinned`, `pinned_at`); Home shows them. New batches are pinned and
  evict the oldest pin. Rubrics carry `pinned` without a cap.
- Samples reset to their initial state on every API start (`MARKER_RESET_SAMPLES_ON_START`) and via
  `POST /api/v1/samples/reset`, so a demo can mark them again; tutor-created data is kept.
- Library rubrics for the samples are files in `app/sample/rubrics/` parsed by the local parser; an
  ambiguous file stops the seed instead of loading a wrong rubric.
- The FakeLLM is available only when `MARKER_ENV=test`.

## Consequences

- Sample numbers are small (5/4/5 submissions) but every count reconciles with real rows.
- Changing sample content means editing `app/sample/documents.py` / `manifest.py` and re-running
  `scripts/build_sample_files.py` and the seeder.
- Migration `0004_sample_data` removes the legacy fixture batches from existing databases.
