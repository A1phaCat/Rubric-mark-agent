import asyncio
from collections import defaultdict
from typing import Any, DefaultDict


class EventBus:
    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers[channel]):
            queue.put_nowait(event)

    def subscribe(self, channel: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._subscribers[channel]:
            self._subscribers[channel].remove(queue)


event_bus = EventBus()
