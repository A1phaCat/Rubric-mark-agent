# ADR 0002: SQLite job queue

Status: accepted, 2026-10-18

Use the `jobs` table with enqueue, atomic lease, heartbeat, bounded retry and terminal failure. Run one worker process with a small configurable pool of concurrent slots. Use WAL and a 5-second busy timeout; never hold a transaction across extraction, OCR or an LLM request. Every slot has a distinct lease owner and renews its lease during long provider calls, preventing duplicate grading after the initial lease period expires.

Consequences: no Redis/Celery deployment is required. Handlers must be idempotent because an expired lease can be reclaimed.

Retries happen in one layer per kind of failure (2026-10): provider rate limits, overload and timeouts are retried inside the LLM client, honouring `Retry-After`, behind one process-wide gate that caps calls in flight across all slots and pauses every slot after a 429; invalid model output is retried once by grading; the job queue re-runs a job only after an unexpected crash. Errors marked `final` (wrong key or model, provider still failing after its retries, output rejected twice) fail the job on the first attempt. A slot that cannot renew its lease stops before the lease expires, and a unique index on `ai_results (submission_id, criterion_id)` rejects a second result for the same criterion.
