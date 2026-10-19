# ADR 0002: SQLite job queue

Status: accepted, 2026-10-18

Use the `jobs` table with enqueue, short lease, heartbeat, bounded retry and terminal failure. Run one worker process. Use WAL and a 5-second busy timeout; never hold a transaction across extraction, OCR or an LLM request.

Consequences: no Redis/Celery deployment is required. Handlers must be idempotent because an expired lease can be reclaimed.

