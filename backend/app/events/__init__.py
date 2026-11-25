"""Progress events.

The SSE endpoint (``GET /api/v1/batches/{id}/events``) reads batch state from the
database rather than an in-memory bus, because the worker runs in a separate process.
"""
