# ADR 0002: SQLite job queue

Status: accepted, 2026-10-18

Use the `jobs` table with enqueue, atomic lease, heartbeat, bounded retry and terminal failure. Run one worker process with a small configurable pool of concurrent slots. Use WAL and a 5-second busy timeout; never hold a transaction across extraction, OCR or an LLM request. Every slot has a distinct lease owner and renews its lease during long provider calls, preventing duplicate grading after the initial lease period expires.

Consequences: no Redis/Celery deployment is required. Handlers must be idempotent because an expired lease can be reclaimed.

