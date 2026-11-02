# AI-assisted marker

Local-first skeleton for a University of Sydney tutor workflow: create a batch, ingest submissions, generate criterion-level evidence and score suggestions, review them, complete the batch, and export reports.

The product contract is [contracts/openapi.yaml](contracts/openapi.yaml), the module map is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and the frozen UI baseline is `prototype/`. Do not edit the prototype.

## Quick start

Requirements: **Python 3.12** (3.13+ does not work: `fastembed==0.3.6` needs Python < 3.13), Node 20+ for
browser tests, and GNU Make optionally. On Windows, call `python scripts/tasks.py <target>` instead of
`make <target>`. For a brand-new machine, follow [Fresh machine from zero](#fresh-machine-from-zero).

```text
cp .env.example .env                                    # optional local settings (never commit .env)
python3.12 -m venv .venv
.venv/bin/python -m pip install -e "backend[dev]"      # Windows: .venv\Scripts\python
.venv/bin/python scripts/tasks.py seed                  # migrate, then load the sample rubrics and batches
.venv/bin/python scripts/tasks.py dev                   # migrate, API on :8000 and the job worker
```

Before starting a real grading run, edit `.env` and set `MARKER_LLM`, `MARKER_AI_BASE_URL`,
`MARKER_AI_API_KEY`, and `MARKER_AI_MODEL` for your OpenAI-compatible provider. For a fully
offline run, the deterministic FakeLLM is used, which the code only allows together with
`MARKER_ENV=test` (set both `MARKER_ENV=test` and `MARKER_LLM=fake`; never for real marking).

On Windows PowerShell, use `.venv\Scripts\python.exe` in place of `python` after creating the
virtual environment, and call `python scripts/tasks.py <target>` instead of `make <target>`.

Open <http://127.0.0.1:8000/>. The API contract is exposed at `/api/v1/openapi.json`; health is `/healthz`.

## Fresh machine from zero

Tested on Linux with Python 3.12 and Node 20. Nothing below needs an API key.

1. **Python 3.12.** Check with `python3.12 --version`. If it is missing, install it from python.org,
   `brew install python@3.12` (macOS), `sudo apt install python3.12 python3.12-venv` (Ubuntu with the
   deadsnakes PPA if needed), or let [uv](https://docs.astral.sh/uv/) fetch it: `uv python install 3.12`.
2. **Clone and create the virtual environment** at `.venv/` in the repository root (the Playwright
   config and the commands below expect that path):

   ```text
   git clone https://github.com/A1phaCat/Rubric-mark-agent.git
   cd Rubric-mark-agent
   python3.12 -m venv .venv            # or: uv venv -p 3.12 .venv
   .venv/bin/python -m pip install -U pip
   .venv/bin/python -m pip install -e "backend[dev]"
   ```

   With uv, the install step is `uv pip install -p .venv/bin/python -e "backend[dev]"`.
   On Windows use `py -3.12 -m venv .venv` and `.venv\Scripts\python` everywhere.
3. **Database and samples.** `.venv/bin/python scripts/tasks.py seed` runs every Alembic migration on a new
   `data/db/marker.sqlite3` and loads the samples. Deleting `data/` and re-running it gives a clean start.
4. **Run.** `.venv/bin/python scripts/tasks.py dev` starts the API and one worker process. Queued batches
   are processed only while the worker runs (`make api` alone never grades anything).
5. **Backend tests** (offline, FakeLLM): `.venv/bin/python scripts/tasks.py test`
   (= `make test PYTHON=.venv/bin/python`).
6. **Browser tests.** Install Node 20+, then:

   ```text
   npm ci
   npx playwright install chromium     # add --with-deps on a bare Linux box
   npx playwright test tests/e2e        # = make e2e
   ```

   Playwright starts `scripts/tasks.py e2e-server` (migrate + seed + API + worker with `MARKER_ENV=test`)
   on a throwaway database in `data/e2e/`, so your own `data/` is never touched. **Stop any `make dev`
   server on port 8000 first**: Playwright reuses a running server, and a normal dev server has no
   FakeLLM. `make visual` compares against the frozen screenshots in `prototype/`.
7. **First real grading run** downloads the local embedding model into `data/cache/fastembed`.
8. **AI provider keys** are entered in the app (account menu) and stored server-side. Never commit them or
   put them in `.env` files that are tracked.

**Token cost.** Each model call's cost is estimated from its token counts with the price table in
`backend/app/llm/pricing.json` (USD per 1M tokens, with source links and the date it was checked).
Set `MARKER_PRICING_FILE=/path/to/prices.json` to use your own table, e.g. for university-gateway or Azure
deployment names. Calls to models missing from the table are shown as *unpriced*, never as $0. The batch
status page shows ≈ $/submission, and the batch results page has an *AI usage & cost* card; the numbers
come from `GET /api/v1/batches/{id}/usage`.

Run modes:

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

### Canvas

Canvas is optional and off by default. Configure it in **Settings → Canvas** (HTTPS base URL plus an
access token, stored with the OS secret store) or with environment variables:

```text
MARKER_CANVAS_BASE_URL=https://canvas.example.edu   # live Canvas REST API
MARKER_CANVAS_TOKEN=...                             # never commit; env or OS secret store only
MARKER_CANVAS_OFFLINE_DIR=data/canvas-offline       # or: a Canvas export folder, no network
```

Without credentials, `python scripts/build_canvas_offline.py` builds an offline export from the sample
rubrics and files; point `MARKER_CANVAS_OFFLINE_DIR` at it and restart the API. Upload → *From a Canvas
assignment* imports the assignment rubric and submitted files into a new batch (Canvas user ids only, no
names) and starts marking. Results → **Send to Canvas…** always shows a dry-run preview first; only
confirmed submissions are pushed, and a live push is refused unless the assignment posts grades
manually, so drafts stay hidden from students. Offline pushes are appended to `grade-pushes.jsonl`.

### Real-data import and evaluation

`scripts/import_real_submissions.py --source <folder or .zip>` (needs `pip install -e "backend[import]"`)
de-identifies every PDF (IDs, names, e-mails, phones → keyed pseudonyms), re-renders it, groups one
batch per assignment and pairs it with the closest library rubric (`data/import/pairing.json`). Source
datasets stay outside the repository and nothing under `data/` is committed.

`eval/run.py` (needs `pip install -e "backend[eval]"`, run from `backend/`) reports tokens and cost per
report, run-to-run consistency and the B2 baseline (the same model scoring the whole report in one call):

```text
python ../eval/run.py primary --batch <batch_id> --repeats 3 --allow-restart [--provider configured]
python ../eval/run.py scale --sample 200 --batches 4
```

`--provider dryrun` (default, no key) sends the real prompts to a metering stub: input tokens are a
tokenizer estimate, output tokens and scores are placeholders and every output is labelled as an
estimate. `--provider configured` uses the configured model and its reported usage. Outputs (CSV, JSON,
PNG) go to `eval/out/` (ignored) or `--out`.

## Directory map

- `prototype/`: frozen reference UI; never used as runtime writable storage.
- `frontend/`: working pages; `js/api.js` is the only browser API client and `js/render-*.js` render pages from it.
- `backend/`: FastAPI application, migrations, module-local tests and `app/sample/` (sample data loader and files).
- `contracts/`: HTTP/error/LLM schemas, the shared external contract.
- `docs/`: review, architecture and ADRs.
- `tests/`: cross-cutting architecture, browser and visual tests.
- `scripts/`: cross-platform task, reset and sample-file build entrypoints.
- `eval/`: cost / consistency / B2 baseline runner and metrics; private datasets and outputs are ignored.
- `data/`: generated runtime data only and ignored by Git.

The local MVP includes deterministic structure-aware rubric parsing, page-aware PDF/DOCX/TXT extraction, and criterion-level hybrid vector/BM25 RAG with verbatim evidence verification. Submission chunks are embedded locally with `BAAI/bge-small-en-v1.5` and cached under `data/index/`. An independent Evidence Gate reads every retrieved candidate, maps zero to five non-redundant passages to the rubric's fixed aspects, and builds a persisted coverage matrix before the grader sees the evidence. Evidence count is never treated as sufficiency. OpenAI-compatible grading is supported; the FakeLLM exists for tests only. Production OCR, FTS5 and production report composition remain post-MVP.

The first real grading run downloads the local embedding model into `data/cache/fastembed`; later runs reuse it. The worker processes three submissions concurrently by default; set `MARKER_WORKER_CONCURRENCY` from 1–8 to match the provider rate limit and local machine. Each slot atomically leases a distinct job and renews its lease during long model calls. Other optional settings are `MARKER_EMBEDDING_MODEL`, `MARKER_EMBEDDING_THREADS`, `MARKER_RETRIEVAL_CANDIDATE_LIMIT`, and `MARKER_EVIDENCE_TOP_K`.

