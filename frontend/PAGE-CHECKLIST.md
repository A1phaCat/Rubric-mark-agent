# Frontend parity checklist

Shared done condition: the page looks and behaves like its counterpart in `prototype/`, receives all data through `api.js`, handles loading/empty/error, works at 390 px, and has an accepted visual-diff result. No page embeds display data; the sample batches are database rows (ADR 0005).

| Page | API data | Current wiring |
|---|---|---|
| Home | me, summary, queue, batches, rubrics | Fully rendered from the API (`render-home.js`); pinned batches first |
| Setup | rubric CRUD, draft batch, files, start | Parse, create rubric, create batch, upload and start use the API; Canvas hidden |
| Rubric import | parse, parse-file, rubric create | Upload and paste go through the parser API; Save creates a pinned library rubric; Canvas hidden |
| Batch status | batch, submissions (filters), retry, pin | Rendered from the API; URL-backed filters; polling while processing |
| Review | review, criterion PATCH, confirm, queue/next | API-driven; manual-marking mode for files without text; Skip/Next follow the DB queue |
| Results | results, CSV, finalise/reopen | Rendered from the API (`render-results.js`) |
| Mark report | report (internal/student) | Rendered from the API (`render-report.js`); print for PDF |
| Rubrics | rubric CRUD, pin | List, edit (new version), delete and pin use the API |
| All batches | batch list, pin, cancel, delete | Rendered from the API; pinned first |
