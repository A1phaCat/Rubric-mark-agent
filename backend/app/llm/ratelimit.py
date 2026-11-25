"""In-process rate control for provider calls; replace behind this interface for distributed deployment."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self.interval = 1.0 / requests_per_second
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class ProviderGate:
    """Process-wide limit on provider calls, shared by every worker slot.

    Each worker slot runs its own thread and event loop, so asyncio primitives cannot be
    shared between them; this gate uses a thread semaphore plus one shared cool-down. A
    429 seen by any slot pauses new calls from all slots until the provider's
    ``Retry-After`` has passed, instead of every slot hitting the limit on its own.
    """

    def __init__(self, max_in_flight: int) -> None:
        self.max_in_flight = max(1, int(max_in_flight))
        self._slots = threading.BoundedSemaphore(self.max_in_flight)
        self._lock = threading.Lock()
        self._cool_until = 0.0
        self.in_flight = 0

    def cool_down(self, seconds: float) -> None:
        with self._lock:
            self._cool_until = max(self._cool_until, time.monotonic() + max(0.0, seconds))

    def cooling_for(self) -> float:
        with self._lock:
            return max(0.0, self._cool_until - time.monotonic())

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        # Poll instead of blocking a thread so a cancelled task stops waiting at once.
        while True:
            wait = self.cooling_for()
            if wait > 0:
                await asyncio.sleep(min(wait, 1.0))
                continue
            if self._slots.acquire(blocking=False):
                break
            await asyncio.sleep(0.05)
        with self._lock:
            self.in_flight += 1
        try:
            yield
        finally:
            with self._lock:
                self.in_flight -= 1
            self._slots.release()


_GATES: dict[int, ProviderGate] = {}
_GATES_LOCK = threading.Lock()


def provider_gate(max_in_flight: int) -> ProviderGate:
    """The shared gate for this process (one per configured limit)."""

    with _GATES_LOCK:
        gate = _GATES.get(max_in_flight)
        if gate is None:
            gate = _GATES[max_in_flight] = ProviderGate(max_in_flight)
        return gate
