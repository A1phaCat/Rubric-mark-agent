# ADR 0003: Module boundaries and ownership

Status: accepted, 2026-10-18

Dependency direction is `api → services → (domain, db.repositories, jobs.queue enqueue-only, events)` and `jobs.handlers → services + processing modules`. Processing order is ingest → extract → retrieval → grading → report. Domain imports no infrastructure. Only `llm/` contacts providers; only `frontend/js/api.js` knows backend URLs.

Each mutable resource has one writer: rubric service owns rubric versions; batch service owns batches/snapshots/status; submission service owns submissions/file links; extract owns immutable document versions; grading owns AI results/evidence; review service owns scores/comments/confirmation; report owns rendered artifacts; settings service owns provider settings; job queue owns jobs. Other modules read through a public service or repository interface.

Public module types live in module `__init__.py`, `interfaces.py`, domain, or contracts. `_internal/` and underscore-prefixed names are private. Architecture tests enforce domain independence, processing isolation and provider-network isolation.

