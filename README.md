# AI-assisted marker

Local-first skeleton for a University of Sydney tutor workflow: create a batch, ingest submissions, generate criterion-level evidence and score suggestions, review them, complete the batch, and export reports.

The product contract is [contracts/openapi.yaml](contracts/openapi.yaml), the module map is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and the frozen UI baseline is `prototype/`. Do not edit the prototype.

## Quick start

Requirements: Python 3.9+ (Python 3.11 recommended), Node 20+ for browser tests, and GNU Make optionally.

On macOS or Linux, create the local environment file, install the backend, initialise the database,
and start the API plus worker with:

```bash
cp .env.example .env

python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"

python scripts/tasks.py migrate
python scripts/tasks.py seed
python scripts/tasks.py dev
```

Before starting a real grading run, edit `.env` and set `MARKER_LLM`, `MARKER_AI_BASE_URL`,
`MARKER_AI_API_KEY`, and `MARKER_AI_MODEL` for your OpenAI-compatible provider. For a fully
offline development run, set `MARKER_LLM=fake` instead.

On Windows PowerShell, use `.venv\Scripts\python.exe` in place of `python` after creating the
virtual environment, and call `python scripts/tasks.py <target>` instead of `make <target>`.

Open <http://127.0.0.1:8000/>. The API contract is exposed at `/api/v1/openapi.json`; health is `/healthz`.

Run modes:

- **mock:** `python scripts/static_server.py`, then open `http://127.0.0.1:4173/00-home.html?mocks=1`; frontend + shared fixtures, no backend.
- **local-fake:** set `MARKER_LLM=fake`, run `make dev`; backend, DB worker and deterministic offline FakeLLM.
- **local-real:** set `MARKER_LLM=azure|minimax|openai|anthropic` plus server-side endpoint/key variables, then run `make dev`; Anthropic is currently a typed stub.

Useful commands:

```text
make migrate        # Alembic upgrade
make seed           # regenerate fixtures and seed SQLite
make api            # API/static server only
make worker         # one DB-queue worker
make test           # unit + contract + architecture
make lint           # Ruff + strict mypy scope
make screenshots    # one-time frozen baseline capture
make e2e            # local-fake flow and nine-page smoke
make visual         # baseline comparison and diff percentages
make check          # complete available validation
```

To remove locally generated test batches, uploaded files, rubrics, jobs, indexes and reports while
keeping the seeded demo data and saved AI provider settings, stop the dev server and run:

```powershell
.\.venv\Scripts\python.exe scripts\reset_local_data.py --yes
```

## Directory map

- `prototype/`: frozen reference UI; never used as runtime writable storage.
- `frontend/`: working copy and the single browser API adapter.
- `backend/`: FastAPI application, migrations and module-local tests.
- `contracts/`: HTTP/error/LLM schemas, the shared external contract.
- `fixtures/demo/`: deterministic data for mock, seed, FakeLLM and contract tests.
- `docs/`: review, architecture and ADRs.
- `tests/`: cross-cutting architecture, browser and visual tests.
- `scripts/`: cross-platform task, fixture and static-server entrypoints.
- `eval/`: golden-set runner skeleton; private datasets are ignored.
- `data/`: generated runtime data only and ignored by Git.

The local MVP includes deterministic structure-aware rubric parsing, page-aware PDF/DOCX/TXT extraction, and criterion-level hybrid vector/BM25 RAG with verbatim evidence verification. Submission chunks are embedded locally with `BAAI/bge-small-en-v1.5` and cached under `data/index/`. An independent Evidence Gate reads every retrieved candidate, maps zero to five non-redundant passages to the rubric's fixed aspects, and builds a persisted coverage matrix before the grader sees the evidence. Evidence count is never treated as sufficiency. FakeLLM and OpenAI-compatible grading are supported. Production OCR, FTS5 and production report composition remain post-MVP.

The first real grading run downloads the local embedding model into `data/cache/fastembed`; later runs reuse it. Optional settings are `MARKER_EMBEDDING_MODEL`, `MARKER_EMBEDDING_THREADS`, `MARKER_RETRIEVAL_CANDIDATE_LIMIT`, and `MARKER_EVIDENCE_TOP_K`.

