# ADR 0004: Runtime data partitions and immutable evidence

Status: accepted, 2026-10-18

All runtime writes live below `data/`. Submission paths use only batch IDs and SHA-256 hashes. Extracted documents are immutable `vN` JSON records; evidence stores the referenced document version and offsets. Re-extraction creates another version and invalidates/regrades dependent AI results.

Logs never contain student text, rubric text or credentials. Generated reports/exports can be invalidated on reopen without changing source files or review audit records.
