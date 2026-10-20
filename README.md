# AI-assisted marker

Local-first skeleton for a University of Sydney tutor workflow: create a batch, ingest submissions, generate criterion-level evidence and score suggestions, review them, complete the batch, and export reports.

The product contract is [contracts/openapi.yaml](contracts/openapi.yaml), the module map is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and the frozen UI baseline is `prototype/`. Do not edit the prototype.

## Quick start

Requirements: Python 3.9+, Node 20+ for browser tests, and GNU Make optionally. On Windows, call `python scripts/tasks.py <target>` instead of `make <target>`.

```text
python -m venv .venv
.venv/Scripts/python -m pip install -e "backend[dev]"
.venv/Scripts/python scripts/tasks.py migrate
.venv/Scripts/python scripts/tasks.py seed   # load the sample rubrics and batches
.venv/Scripts/python scripts/tasks.py dev
```

Open <http://127.0.0.1:8000/>. The API contract is exposed at `/api/v1/openapi.json`; health is `/healthz`.

Run modes:

- **local:** run `make dev`, then choose the AI provider (university gateway, Azure, MiniMax, OpenAI) and save
  its key from the account menu; keys stay server-side. Everything the pages show is read from the local
  SQLite database through the API — there is no mock or fixture mode.
- **tests:** `MARKER_ENV=test` enables the deterministic offline FakeLLM for pytest and Playwright only. It
  cannot be selected outside the test environment.

### Sample data

`make seed` (or `python -m app.sample.seed` in `backend/`) loads sample data into the database:
six library rubrics and three pinned sample batches — *ASGN2 Critical Essay* (in review, including one
scanned submission that needs manual marking), *ASGN1 Literature Review* (all confirmed, still editable) and
*Quiz 3 Short Answer* (finalised and locked). The submission files are real PDFs/DOCX under
`backend/app/sample/files/`; they are stored and text-extracted exactly like uploads, tutor edits and
confirmations go through the review service, and the evidence quotes are located in the extracted text. Only
the AI grading step is replayed from results recorded in `backend/app/sample/manifest.py`, so the samples
load offline and identically everywhere. Re-running the seed replaces the samples and leaves your own
batches, rubrics and AI settings alone.

Batches and rubrics you create are saved in the same database and **pinned** to the top of Home, *All
batches* and the rubric library; pin or unpin them from those lists. To change the sample texts, edit
`backend/app/sample/documents.py` and rebuild the files with `python scripts/build_sample_files.py`
(needs `reportlab` and `Pillow`).

Useful commands:

```text
make migrate        # Alembic upgrade
make seed           # load or reload the sample rubrics and batches
make api            # API/static server only
make worker         # one DB-queue worker
make test           # unit + contract + architecture
make lint           # Ruff + strict mypy scope
make screenshots    # one-time frozen baseline capture
make e2e            # Playwright: pages render DB data; create → review → confirm flow
make visual         # baseline comparison and diff percentages
make check          # complete available validation
```

To remove locally generated batches, uploaded files, rubrics, jobs, indexes and reports, reload the sample
data and keep the saved AI provider settings, stop the dev server and run:

```powershell
.\.venv\Scripts\python.exe scripts\reset_local_data.py --yes
```

## Directory map

- `prototype/`: frozen reference UI; never used as runtime writable storage.
- `frontend/`: working pages; `js/api.js` is the only browser API client and `js/render-*.js` render pages from it.
- `backend/`: FastAPI application, migrations, module-local tests and `app/sample/` (sample data loader and files).
- `contracts/`: HTTP/error/LLM schemas, the shared external contract.
- `docs/`: review, architecture and ADRs.
- `tests/`: cross-cutting architecture, browser and visual tests.
- `scripts/`: cross-platform task, reset and sample-file build entrypoints.
- `eval/`: golden-set runner skeleton; private datasets are ignored.
- `data/`: generated runtime data only and ignored by Git.

The local MVP includes deterministic structure-aware rubric parsing, page-aware PDF/DOCX/TXT extraction, and criterion-level hybrid vector/BM25 RAG with verbatim evidence verification. Submission chunks are embedded locally with `BAAI/bge-small-en-v1.5` and cached under `data/index/`. An independent Evidence Gate reads every retrieved candidate, maps zero to five non-redundant passages to the rubric's fixed aspects, and builds a persisted coverage matrix before the grader sees the evidence. Evidence count is never treated as sufficiency. OpenAI-compatible grading is supported; the FakeLLM exists for tests only. Production OCR, FTS5 and production report composition remain post-MVP.

The first real grading run downloads the local embedding model into `data/cache/fastembed`; later runs reuse it. Optional settings are `MARKER_EMBEDDING_MODEL`, `MARKER_EMBEDDING_THREADS`, `MARKER_RETRIEVAL_CANDIDATE_LIMIT`, and `MARKER_EVIDENCE_TOP_K`.

