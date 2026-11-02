"""How many evidence agents are running right now in this process, per submission.

The worker publishes this in its heartbeat so the batch page can show live agent counts.
"""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

_lock = threading.Lock()
_running: Counter[str] = Counter()


@contextmanager
def running(submission_id: str | None) -> Iterator[None]:
    key = submission_id or ""
    with _lock:
        _running[key] += 1
    try:
        yield
    finally:
        with _lock:
            _running[key] -= 1
            if _running[key] <= 0:
                del _running[key]


def snapshot() -> dict[str, int]:
    with _lock:
        return {key: count for key, count in _running.items() if key}
