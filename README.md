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


## mac run

```text
.venv/bin/python -m pip install -e "backend[dev]"
.venv/bin/python scripts/tasks.py migrate
.venv/bin/python scripts/tasks.py dev
Run modes:
```



- **local:** run `make dev`, then choose the AI provider (university gateway, Azure, MiniMax, OpenAI) and save
  its key from the account menu; keys stay server-side. Everything the pages show is read from the local
  SQLite database through the API — there is no mock or fixture mode.
- **tests:** `MARKER_ENV=test` enables the deterministic offline FakeLLM for pytest and Playwright only. It
  cannot be selected outside the test environment.

### Sample data

Sample data lives in the database like everything else: six library rubrics and three sample
batches — *ASGN2 Critical Essay* (in review, including one scanned submission that needs manual
marking), *ASGN1 Literature Review* (all confirmed, still editable) and *Quiz 3 Short Answer*
(finalised and locked). The submission files are real PDFs/DOCX under `backend/app/sample/files/`;
they are stored and text-extracted like uploads, tutor edits and confirmations go through the review
service, and evidence quotes are located in the extracted text. Only AI grading is replayed from
results recorded in `backend/app/sample/manifest.py`, so the samples load offline.

**The samples reset to their starting state every time the API starts** (`make dev` / `make api`),
and on demand with **↺ Reset samples** on Home or `make seed`. Your own batches, rubrics and AI
settings are kept. Set `MARKER_RESET_SAMPLES_ON_START=false` to keep sample marks across restarts.

**Pinning:** at most three batches are pinned, and Home shows those three (if fewer are pinned, the
newest batches fill the remaining places). A new batch is pinned automatically; pinning a fourth batch
unpins the one pinned longest ago. Resetting the samples pins the three samples again.

**Preloaded rubrics:** every file in `backend/app/sample/rubrics/` is loaded into the library — JSON
(exact; recommended), a Markdown table, or a CSV/TSV exported from Excel. See that folder's README and
the `_template.json` / `_template.csv` files. To change the sample texts, edit
`backend/app/sample/documents.py` and rebuild the files with `python scripts/build_sample_files.py`
(needs `reportlab` and `Pillow`).

Useful commands:

```text
make migrate        # Alembic upgrade
make seed           # reset the sample batches and reload rubrics from backend/app/sample/rubrics/
make api            # API/static server only
make worker         # one DB-queue worker process with bounded concurrent slots
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

The first real grading run downloads the local embedding model into `data/cache/fastembed`; later runs reuse it. The worker processes three submissions concurrently by default; set `MARKER_WORKER_CONCURRENCY` from 1–8 to match the provider rate limit and local machine. Each slot atomically leases a distinct job and renews its lease during long model calls. Other optional settings are `MARKER_EMBEDDING_MODEL`, `MARKER_EMBEDDING_THREADS`, `MARKER_RETRIEVAL_CANDIDATE_LIMIT`, and `MARKER_EVIDENCE_TOP_K`.

